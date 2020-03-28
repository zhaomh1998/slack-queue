import os
import logging
from flask import Flask, request, make_response, Response
from slack import WebClient
from slackeventsapi import SlackEventAdapter
import ssl as ssl_lib
import certifi
import json
import nest_asyncio
import ui

# https://github.com/spyder-ide/spyder/issues/7096
# Resolved "Event loop already running" when running multiple API calls at same time
nest_asyncio.apply()

INTERACTION_STUDENT_REFRESH = 'RefreshHomePage'
INTERACTION_STUDENT_CONNECT_TA = 'ConnectTA'
INTERACTION_STUDENT_DEQUEUE = 'DequeueConnectTA'
INTERACTION_STUDENT_END_CHAT = 'EndConnectTA'
INTERACTION_TA_LOGIN = 'TALogIn'
INTERACTION_TA_DONE = 'TADone'
INTERACTION_TA_PASS = 'TAPass'
INTERACTION_ADMIN_RESET = 'AdminReset'
INPUT_TA_PASS_ID = 'TAPassID'
TA_PASSWORD = os.environ["SLACK_TA_PASSWD"]

free_ta = []
busy_ta = []
student_queue = []
tas = dict()
id_to_name = dict()
id_to_teamId = dict()
student_status = dict()  # TODO: Refactor this into a class
student_ta_connection = dict()


class TA:
    def __init__(self, uid):
        self.uid = uid
        self.busy = False
        self.helping_who = 'ERR: NOT HELPING ANYONE'
        self.active = False
        self.name = get_user_name(uid)
        self.im = slack_web_client.conversations_open(users=[self.uid])['channel']['id']

    def assign(self, student_id):
        assert not self.busy
        self.busy = True
        self.helping_who = student_id
        slack_web_client.chat_postMessage(
            channel=self.im,
            blocks=get_request_block(self.helping_who)
        )

    def complete(self):
        assert self.busy
        self.busy = False
        student_status[self.helping_who] = 'idle'
        self.helping_who = 'ERR: NOT HELPING ANYONE'

    def toggle_active(self):
        self.active = not self.active
        if self.active:
            slack_web_client.chat_postMessage(
                channel=self.im,
                text="You have started accepting requests!"
            )
        else:
            slack_web_client.chat_postMessage(
                channel=self.im,
                text="You are no longer accepting requests!"
            )

    def get_status_text(self, ta_view):
        if self.busy:
            if ta_view:
                return f'(Busy) {self.name} currently helping {get_user_name(self.helping_who)}'
            else:
                return f'(Busy) {self.name} currently helping a student'
        else:
            return f'{self.name}'

    def reassign(self):
        # Notify student, change student_ta_connection, change self status, etc
        raise NotImplementedError()


# Initialize a Flask app to host the events adapter
app = Flask(__name__)
slack_events_adapter = SlackEventAdapter(os.environ["SLACK_SIGNING_SECRET"], "/slack/events", app)

# Initialize a Web API client
# Note: Slack WebClient need to be in async mode in order to get two request at same time to work
# https://github.com/slackapi/python-slackclient/issues/429
slack_web_client = WebClient(token=os.environ['SLACK_BOT_TOKEN'])  # , run_async=True)
bot_user = slack_web_client.auth_test()
all_users = slack_web_client.users_list()


@slack_events_adapter.on("app_home_opened")
def home_open(payload):
    event = payload.get("event", {})
    user_id = event.get("user")
    print(f"Home opened from {user_id}")
    slack_web_client.views_publish(user_id=user_id,
                                   view=get_app_home(user_id))


@slack_events_adapter.on("app_mention")
def mentioned(payload):
    event = payload.get("event", {})
    user_id = event.get("user")
    channel_id = event.get("channel")
    text = event.get("text")
    print("Mention!")
    slack_web_client.chat_postMessage(
        channel=channel_id,
        text="Please find me under Apps on your sidebar"
    )


# @slack_events_adapter.on("message")
# def message(payload):
#     event = payload.get("event", {})
#     user_id = event.get("user")
#     # Disregard message from None which could be a message-delete event
#     # Disregard own message
#     if user_id is None or user_id == bot_user.data['user_id']:
#         return
#     channel_id = event.get("channel")
#     text = event.get("text")

# debug_print_msg(payload)

# Views
def get_app_home(user_id):
    if user_id not in student_status.keys():
        student_status[user_id] = 'idle'
    current_status = student_status[user_id]

    is_ta = True if user_id in tas else False

    # Info
    blocks = [
        ui.welcome_title(get_user_name(user_id)),
        ui.greeting(is_ta),
    ]

    # Control Panel for TA Only
    if is_ta:
        blocks += [
            ui.DIVIDER,
            ui.text(f"Student Queue Length: {len(student_queue)}"),
            ui.actions([ui.button("Admin Reset", INTERACTION_ADMIN_RESET)])
        ]

    blocks += [
        ui.DIVIDER,
        ui.active_ta(len(free_ta) + len(busy_ta))
    ]
    blocks += [ui.text(ta.name) for ta in free_ta]
    blocks += [ui.text(ta.get_status_text(ta_view=is_ta)) for ta in busy_ta]
    blocks += [ui.DIVIDER]

    # Functional
    if current_status == 'idle':
        blocks += [ui.text("Click `Connect to TA` to request a TA")]
        blocks += [ui.actions([
            ui.button("Connect to a TA", INTERACTION_STUDENT_CONNECT_TA),
            ui.button("TA Login", INTERACTION_TA_LOGIN),
        ])]
    elif current_status == 'queued':
        blocks += [ui.text(f"You are #{student_queue.index(user_id) + 1} in the queue"),
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
        raise ValueError(f"Unexpected current_status: {current_status} for student {get_user_name(user_id)}")

    blocks += [ui.actions([ui.button("Refresh", INTERACTION_STUDENT_REFRESH)])]
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


def get_request_block(student_uid):
    student_name = get_user_name(student_uid)
    student_im = f'slack://user?team={get_user_teamid(student_uid)}&id={student_uid}'
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"You have a new request from {student_name}:\n*<{student_im}|Click to chat with {student_name} >*"
            }
        },
        # TODO
        # {
        #     "type": "section",
        #     "fields": [
        #         {
        #             "type": "mrkdwn",
        #             "text": "*Question Brief:*\n<FIXME>"
        #         }
        #     ]
        # },

        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "emoji": True,
                        "text": "Finished!"
                    },
                    "style": "primary",
                    "value": INTERACTION_TA_DONE
                },
                # {
                #     "type": "button",
                #     "text": {
                #         "type": "plain_text",
                #         "emoji": True,
                #         "text": "Pass to Other TA"
                #     },
                #     "style": "danger",
                #     "value": INTERACTION_TA_PASS
                # }
            ]
        }
    ]


def debug_print_msg(payload):
    event = payload.get("event", {})
    user_id = event.get("user")
    # Disregard own message
    if user_id == bot_user.data['user_id']:
        return
    channel_id = event.get("channel")
    text = event.get("text")

    slack_web_client.chat_postMessage(
        channel=channel_id,
        text=f"""Hello! :tada: I received from {get_user_name(user_id)} on channel {get_channel_name(channel_id)}! Event type is {event.get("type")}
{text}
"""
    )
    slack_web_client.chat_postMessage(
        channel=channel_id,
        blocks=get_request_block(user_id)
    )


def disconnect_student(payload):
    raise NotImplementedError()
    user_id = payload['user']['id']
    student_status[user_id] = 'idle'
    slack_web_client.views_publish(user_id=user_id,
                                   view=get_app_home(user_id))
    # TODO: Notify TA connected with this student


def check_student_queue():
    assert len(free_ta) != 0
    if len(student_queue) != 0:
        # Dequeue
        user_id = student_queue[0]
        student_queue.remove(user_id)

        student_status[user_id] = 'busy'
        assigned_ta = free_ta[0]
        assigned_ta.assign(user_id)
        busy_ta.append(assigned_ta)
        free_ta.remove(assigned_ta)
        slack_web_client.views_publish(user_id=user_id,
                                       view=get_app_home(user_id))


# https://api.slack.com/messaging/interactivity
@app.route("/slack/interactive-endpoint", methods=["POST"])
def interactive_test():
    payload = json.loads(request.form["payload"])
    assert payload['type'] in ['block_actions', 'view_submission']
    if payload['type'] == 'view_submission':
        ta_verify_passwd(payload)
    else:
        actions = payload['actions']
        assert len(actions) == 1
        action_value = actions[0]['value']
        if action_value == INTERACTION_STUDENT_REFRESH:
            user_id = payload['user']['id']
            slack_web_client.views_publish(user_id=user_id,
                                           view=get_app_home(user_id))
        if action_value == INTERACTION_STUDENT_CONNECT_TA:
            student_connect(payload)
        elif action_value == INTERACTION_STUDENT_DEQUEUE:
            student_dequeue(payload)
        elif action_value == INTERACTION_STUDENT_END_CHAT:
            disconnect_student(payload)
        elif action_value == INTERACTION_TA_DONE:
            ta_done(payload)
        elif action_value == INTERACTION_TA_PASS:
            ta_pass(payload)
        elif action_value == INTERACTION_TA_LOGIN:
            trigger_id = payload['trigger_id']
            slack_web_client.views_open(trigger_id=trigger_id, view=get_ta_verification())
    # Send an HTTP 200 response with empty body so Slack knows we're done here
    return make_response("", 200)


def ta_verify_passwd(payload):
    print("View submission!")
    user_id = payload['user']['id']
    passwd = payload['view']['state']['values'][INPUT_TA_PASS_ID]['field']['value']
    if passwd == TA_PASSWORD:
        if user_id not in tas:
            tas[user_id] = TA(user_id)
        the_ta = tas[user_id]

        # TA Log on
        if not the_ta.active:
            free_ta.append(the_ta)
            the_ta.toggle_active()
            check_student_queue()
        # TA Log off
        else:
            if the_ta in busy_ta:
                the_ta.complete()
                assert the_ta in busy_ta
                busy_ta.remove(the_ta)
            else:
                assert the_ta in free_ta
                free_ta.remove(the_ta)
            the_ta.toggle_active()
    slack_web_client.views_publish(user_id=user_id,
                                   view=get_app_home(user_id))


def ta_complete(user_id):
    the_ta = tas[user_id]
    the_ta.complete()
    free_ta.append(the_ta)
    busy_ta.remove(the_ta)
    check_student_queue()


def ta_reassign(user_id):
    raise NotImplementedError()
    the_ta = tas[user_id]
    the_ta.reassign()
    free_ta.append(the_ta)
    busy_ta.remove(the_ta)
    check_student_queue()


def ta_pass(payload):
    channel_id = payload['channel']['id']
    msg_ts = payload['message']['ts']
    user_id = payload['user']['id']
    ta_reassign(user_id)
    print("TA Pass to next TA!")
    slack_web_client.chat_delete(
        channel=channel_id,
        ts=msg_ts
    )
    slack_web_client.chat_postMessage(
        channel=channel_id,
        text='TA Pass!')


def ta_done(payload):
    channel_id = payload['channel']['id']
    msg_ts = payload['message']['ts']
    user_id = payload['user']['id']
    student_name = get_user_name(tas[user_id].helping_who)
    ta_complete(user_id)
    print("TA Done!")
    slack_web_client.chat_delete(
        channel=channel_id,
        ts=msg_ts
    )
    slack_web_client.chat_postMessage(
        channel=channel_id,
        text=f'Finished helping {student_name}')


def student_connect(payload):
    user_id = payload['user']['id']
    trigger_id = payload['trigger_id']
    assert student_status[user_id] == 'idle'

    if len(free_ta) == 0:
        student_status[user_id] = 'queued'
        student_queue.append(user_id)
        slack_web_client.views_publish(user_id=user_id,
                                       view=get_app_home(user_id))
    else:
        student_status[user_id] = 'busy'
        assigned_ta = free_ta[0]
        assigned_ta.assign(user_id)
        busy_ta.append(assigned_ta)
        free_ta.remove(assigned_ta)
        slack_web_client.views_publish(user_id=user_id,
                                       view=get_app_home(user_id))
    print("Student connected!")


def student_dequeue(payload):
    user_id = payload['user']['id']
    trigger_id = payload['trigger_id']
    student_queue.remove(user_id)
    student_status[user_id] = 'idle'
    slack_web_client.views_publish(user_id=user_id,
                                   view=get_app_home(user_id))


def get_user_name(user_id):
    if user_id not in id_to_name.keys():
        id_to_name[user_id] = slack_web_client.users_info(user=user_id).data['user']['profile']['display_name']
    return id_to_name[user_id]


def get_user_teamid(user_id):
    if user_id not in id_to_teamId.keys():
        id_to_teamId[user_id] = slack_web_client.users_info(user=user_id).data['user']['team_id']
    return id_to_teamId[user_id]


def get_channel_name(channel_id):
    channel_info = slack_web_client.conversations_info(channel=channel_id).data['channel']
    if channel_info['is_im']:
        im_with = channel_info['user']
        return f'Private Message with {get_user_name(im_with)}'
    else:
        return channel_info['name_normalized']


def is_admin(user_id):
    return True


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())
    ssl_context = ssl_lib.create_default_context(cafile=certifi.where())
    app.run(port=3000)
