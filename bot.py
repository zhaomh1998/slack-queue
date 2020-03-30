import os
import logging
from quart import Quart, request, make_response, Response
# from slackeventsapi import SlackEventAdapter
import ssl as ssl_lib
import certifi
import json
import nest_asyncio
import ui
from time import time, strftime
from manager import QueueManager
from api import *
import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve
#
# # https://github.com/spyder-ide/spyder/issues/7096
# # Resolved "Event loop already running" when running multiple API calls at same time
# nest_asyncio.apply()

TA_PASSWORD = os.environ["SLACK_TA_PASSWD"]

# Initialize a Flask app to host the events adapter
app = Quart(__name__)
# slack_events_adapter = SlackEventAdapter(os.environ["SLACK_SIGNING_SECRET"], "/slack/events", app)
slack = Slack(os.environ['SLACK_BOT_TOKEN'], os.environ["SLACK_SIGNING_SECRET"])
manager = QueueManager(slack)


@app.route("/slack/events", methods=['POST'])
async def slack_event():
    req_header = request.headers
    req_data = await request.data
    # Each request comes with request timestamp and request signature
    # emit an error if the timestamp is out of range
    req_timestamp = req_header.get('X-Slack-Request-Timestamp')
    if abs(time() - int(req_timestamp)) > 60 * 5:
        logger.exception('Invalid request timestamp')
        return await make_response("", 403)

    # Verify the request signature using the app's signing secret
    # emit an error if the signature can't be verified
    req_signature = req_header.get('X-Slack-Signature')
    if not slack.verify_signature(req_timestamp, req_signature, req_data):
        logger.exception('Invalid request signature')
        return await make_response("", 403)

    # Parse the request payload into JSON
    event_data = json.loads(req_data.decode('utf-8'))

    # Echo the URL verification challenge code back to Slack
    if "challenge" in event_data:
        return await make_response(
            event_data.get("challenge"), 200, {"content_type": "application/json"}
        )

    # Parse the Event payload and emit the event to the event listener
    if "event" in event_data:
        event_type = event_data["event"]["type"]
        if event_type == "app_home_opened":
            await home_open(event_data)
        elif event_type == "app_mention":
            await mentioned(event_data)
        elif event_type == "message":
            await on_message(event_data)
        response = await make_response("", 200)
        # response.headers['X-Slack-Powered-By'] = self.package_info
        return response


async def home_open(payload):
    event = payload.get("event", {})
    user_id = event.get("user")
    logger.debug(f"Home opened from {user_id}")
    await slack.send_home_view(user_id, await get_app_home(user_id))


async def mentioned(payload):
    event = payload.get("event", {})
    user_id = event.get("user")
    channel_id = event.get("channel")
    text = event.get("text")
    print("Mention!")
    await slack.send_chat_text(channel_id, "Please find me under Apps on your sidebar")


async def on_message(payload):
    event = payload.get("event", {})
    user_id = event.get("user")
    # Disregard message from None which could be a message-delete event
    # Disregard own message
    if user_id is None or user_id == slack.bot_user.data['user_id']:
        return
    channel_id = event.get("channel")
    text = event.get("text")
    if text == "!h ping":
        await slack.send_chat_text(channel_id, "pong :tada:")
    elif text == "!h reset":
        manager.admin_reset()
    # await debug_print_msg(payload)


# Views
async def get_app_home(user_id):
    current_status = manager.get_student_status(user_id)
    is_ta, is_active = manager.is_ta(user_id)

    # Info
    blocks = [
        ui.welcome_title(await slack.get_user_name(user_id)),
        ui.greeting(is_ta, is_active),
    ]

    # Control Panel for TA Only
    if is_ta:
        blocks += [
            ui.DIVIDER,
            ui.text(f"*{manager.get_queue_length()} Students* waiting in queue"),
            ui.text(await manager.str_queue()),
            ui.actions([ui.button_styled("System States Reset", INTERACTION_ADMIN_RESET, "danger",
                                         ui.reset_confirm())])
        ]

    blocks += [
        ui.DIVIDER,
        ui.active_ta(manager.get_ta_size())
    ]
    blocks += [ui.text(manager.str_free_ta())]
    busy_tas = [await ta.get_status_text(ta_view=is_ta) for ta in manager.pairs.keys()]
    blocks += [ui.list_quote_text(busy_tas)]

    # Functional
    if current_status == 'idle':
        blocks += [ui.actions([
            ui.button_styled(":telephone_receiver: Connect to a TA", INTERACTION_STUDENT_CONNECT_TA, "primary"),
            ui.button(manager.get_ta_login_text(user_id), INTERACTION_TA_LOGIN),
        ])]
    elif current_status == 'queued':
        blocks += [ui.text(f"You are *#{manager.get_queue_position(user_id)}* in the queue"),
                   ui.actions([ui.button("Cancel Request", INTERACTION_STUDENT_DEQUEUE)])
                   ]
    elif current_status == 'busy':
        blocks += [
            ui.text("You are connected with a TA. Look for their direct message in a moment.")
            # TODO: Haven't implemented notify TA so disabled for now
            # {"type": "actions",
            #  "elements": [{"type": "button",
            #                "text": {"type": "plain_text",
            #                         "text": "End Chat",
            #                         "emoji": True},
            #                "value": INTERACTION_STUDENT_END_CHAT}
            #               ]
            #  }
        ]
    else:
        raise ValueError(f"Unexpected current_status: {current_status} for student {await slack.get_user_name(user_id)}")

    blocks += [ui.actions([ui.button(":arrows_counterclockwise: Refresh", INTERACTION_STUDENT_REFRESH)])]
    return {
        "type": "home",
        "blocks": blocks
    }


def get_ta_verification():
    return {
        "type": "modal",
        "title": {
            "type": "plain_text",
            "text": "TA Verification",
            "emoji": True
        },
        "submit": {
            "type": "plain_text",
            "text": "Submit",
            "emoji": True
        },
        "close": {
            "type": "plain_text",
            "text": "Cancel",
            "emoji": True
        },
        "blocks": [
            {
                "type": "input",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "field",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Input TA Secret Password"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "TA Secret Password"
                },
                "block_id": INPUT_TA_PASS_ID
            }
        ]
    }


async def debug_print_msg(payload):
    event = payload.get("event", {})
    user_id = event.get("user")
    # Disregard own message
    if slack.is_this_bot(user_id):
        return
    channel_id = event.get("channel")
    text = event.get("text")
    await slack.send_chat_text(channel_id,
                         f"""Hello! :tada: I received from {await slack.get_user_name(user_id)} on channel {await slack.get_channel_name(channel_id)}! Event type is {event.get("type")}
{text}
""")
    await slack.send_chat_block(channel_id, await slack.get_request_block(user_id))


# def disconnect_student(payload):
#     raise NotImplementedError()
#     user_id = payload['user']['id']
#     student_status[user_id] = 'idle'
#     slack_web_client.views_publish(user_id=user_id,
#                                    view=get_app_home(user_id))
#     # TODO: Notify TA connected with this student


# https://api.slack.com/messaging/interactivity
@app.route("/slack/interactive-endpoint", methods=["POST"])
async def interactive_received():
    payload = json.loads((await request.form)["payload"])
    assert payload['type'] in ['block_actions', 'view_submission']
    if payload['type'] == 'view_submission':
        await ta_verify_passwd(payload)
    else:
        actions = payload['actions']
        assert len(actions) == 1
        action_value = actions[0]['value']
        if action_value == INTERACTION_STUDENT_REFRESH:
            user_id = payload['user']['id']
            await slack.send_home_view(user_id, await get_app_home(user_id))
        if action_value == INTERACTION_STUDENT_CONNECT_TA:
            await student_connect(payload)
        elif action_value == INTERACTION_STUDENT_DEQUEUE:
            await student_dequeue(payload)
        elif action_value == INTERACTION_STUDENT_END_CHAT:
            disconnect_student(payload)
        elif action_value == INTERACTION_TA_DONE:
            await ta_done(payload)
        elif action_value == INTERACTION_TA_PASS:
            ta_pass(payload)
        elif action_value == INTERACTION_TA_LOGIN:
            trigger_id = payload['trigger_id']
            user_id = payload['user']['id']
            if manager.is_ta_active(user_id):
                await manager.ta_login(user_id)
                await slack.send_home_view(user_id, await get_app_home(user_id))
            else:
                await slack.send_modal(trigger_id, get_ta_verification())
        elif action_value == INTERACTION_ADMIN_RESET:
            user_id = payload['user']['id']
            manager.admin_reset()
            await slack.send_home_view(user_id, await get_app_home(user_id))
    # Send an HTTP 200 response with empty body so Slack knows we're done here
    return await make_response("", 200)


async def ta_verify_passwd(payload):
    user_id = payload['user']['id']
    passwd = payload['view']['state']['values'][INPUT_TA_PASS_ID]['field']['value']
    if passwd == TA_PASSWORD:
        await manager.ta_login(user_id)
    await slack.send_home_view(user_id, await get_app_home(user_id))


#

# def ta_reassign(user_id):
#     raise NotImplementedError()
#     the_ta = tas[user_id]
#     the_ta.reassign()
#     free_ta.append(the_ta)
#     busy_ta.remove(the_ta)
#     check_student_queue()
#
#
# def ta_pass(payload):
#     channel_id = payload['channel']['id']
#     msg_ts = payload['message']['ts']
#     user_id = payload['user']['id']
#     ta_reassign(user_id)
#     print("TA Pass to next TA!")
#     slack.delete_chat(channel_id, msg_ts).send_chat_text(channel_id, 'TA Pass!')
#
#
async def ta_done(payload):
    channel_id = payload['channel']['id']
    msg_ts = payload['message']['ts']
    user_id = payload['user']['id']
    student_name = await manager.ta_complete_request(user_id)
    logger.debug(f"{user_id} has finished helping {student_name}")
    await(await slack.delete_chat(channel_id, msg_ts)).send_chat_text(channel_id, f'Finished helping {student_name}!')


async def student_connect(payload):
    user_id = payload['user']['id']
    logger.debug(f"Student {user_id} requests a connection!")
    trigger_id = payload['trigger_id']
    await manager.student_request(user_id, trigger_id)
    await slack.send_home_view(user_id, await get_app_home(user_id))


async def student_dequeue(payload):
    user_id = payload['user']['id']
    logger.debug(f"Student {user_id} removes themselves from queue!")
    trigger_id = payload['trigger_id']
    manager.student_remove_from_queue(user_id, trigger_id)
    await slack.send_home_view(user_id, await get_app_home(user_id))


if __name__ == "__main__":
    # Logging
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fh = logging.FileHandler(strftime("bot_%Y%b%d_%H-%M-%S.log"))
    fh.setLevel(logging.DEBUG)
    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)

    ssl_context = ssl_lib.create_default_context(cafile=certifi.where())
    # app.run(port=3000)
    config = Config()
    config.bind = ["localhost:3000"]
    loop = asyncio.get_event_loop()
    logger.info('Server starting...')
    loop.run_until_complete(serve(app, config))
