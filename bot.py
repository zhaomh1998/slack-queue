import os
import logging
from flask import Flask, request, make_response, Response
from slack import WebClient
from slackeventsapi import SlackEventAdapter
import ssl as ssl_lib
import certifi
import json
import nest_asyncio

# https://github.com/spyder-ide/spyder/issues/7096
# Resolved "Event loop already running" when running multiple API calls at same time
nest_asyncio.apply()

INTERACTION_STUDENT_CONNECT_TA = 'ConnectTA'
INTERACTION_TA_LOGIN = 'TALogIn'
INTERACTION_TA_DONE = 'TADone'
INTERACTION_TA_PASS = 'TAPass'
INPUT_TA_PASS_ID = 'TAPassID'
TA_PASSWORD = os.environ["SLACK_TA_PASSWD"]


class TA:
    def __init__(self, uid):
        self.uid = uid
        self.busy = False
        self.helping_who = None
        self.active = False
        self.name = get_user_name(uid)

    def assign(self, student_id):
        """ Assigns a TA with a student. Returns False if TA is busy. """
        if self.busy:
            return False
        else:
            self.busy = True
            self.helping_who = student_id
            return True

    def complete(self):
        assert self.busy
        self.busy = False
        self.helping_who = None

    def toggle_active(self):
        self.active = not self.active


free_ta = []
busy_ta = []
student_queue = []
tas = dict()
id_to_name = dict()
id_to_teamId = dict()


def get_app_home(user_id):
    blocks = [
        {"type": "section",
         "text": {"type": "mrkdwn", "text": f"Hi {get_user_name(user_id)} :wave:"}
         },
        {"type": "section",
         "text": {"type": "mrkdwn", "text": "I'm here to help you find a TA during lab section"
                  }
         },
        {"type": "divider"},
        {"type": "section",
         "text": {"type": "mrkdwn", "text": f"{len(free_ta) + len(busy_ta)} TAs Active:"}
         }]
    for ta in free_ta:
        blocks.append(
            {"type": "section",
             "text": {"type": "mrkdwn", "text": f"{ta.name}"}}
        )
    for ta in busy_ta:
        blocks.append(
            {"type": "section",
             "text": {"type": "mrkdwn", "text": f"_(Busy) {ta.name}_"}}
        )
    blocks += [
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Connect to a TA",
                        "emoji": True
                    },
                    "value": INTERACTION_STUDENT_CONNECT_TA
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "TA Login",
                        "emoji": True
                    },
                    "value": INTERACTION_TA_LOGIN
                }
            ]
        }
    ]

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
                "text": f"You have a new request from <{student_name}>:\n*<{student_im}|Click to chat with {student_name} >*"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": "*Question Brief:*\n<question brief>"
                }
            ]
        },
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
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "emoji": True,
                        "text": "Pass to Other TA"
                    },
                    "style": "danger",
                    "value": INTERACTION_TA_PASS
                }
            ]
        }
    ]


# Initialize a Flask app to host the events adapter
app = Flask(__name__)
slack_events_adapter = SlackEventAdapter(os.environ["SLACK_SIGNING_SECRET"], "/slack/events", app)

# Initialize a Web API client
slack_web_client = WebClient(token=os.environ['SLACK_BOT_TOKEN'])
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


def process_view_submission(payload):
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


# https://api.slack.com/messaging/interactivity
@app.route("/slack/interactive-endpoint", methods=["POST"])
def interactive_test():
    payload = json.loads(request.form["payload"])
    assert payload['type'] in ['block_actions', 'view_submission']
    if payload['type'] == 'view_submission':
        process_view_submission(payload)
    else:
        # trigger_id = payload['trigger_id']
        # response_url = payload['response_url']
        actions = payload['actions']
        assert len(actions) == 1
        action_value = actions[0]['value']
        if action_value == INTERACTION_STUDENT_CONNECT_TA:
            print("Student request connect to TA!")
        elif action_value == INTERACTION_TA_DONE:
            channel_id = payload['channel']['id']
            msg_ts = payload['message']['ts']
            print("TA Done!")
            slack_web_client.chat_delete(
                channel=channel_id,
                ts=msg_ts
            )
            slack_web_client.chat_postMessage(
                channel=channel_id,
                text='TA Done!')
        elif action_value == INTERACTION_TA_PASS:
            channel_id = payload['channel']['id']
            msg_ts = payload['message']['ts']
            print("TA Pass to next TA!")
            slack_web_client.chat_delete(
                channel=channel_id,
                ts=msg_ts
            )
            slack_web_client.chat_postMessage(
                channel=channel_id,
                text='TA Pass!')
        elif action_value == INTERACTION_TA_LOGIN:
            trigger_id = payload['trigger_id']
            slack_web_client.views_open(trigger_id=trigger_id, view=get_ta_verification())
    # Send an HTTP 200 response with empty body so Slack knows we're done here
    return make_response("", 200)


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


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())
    ssl_context = ssl_lib.create_default_context(cafile=certifi.where())
    app.run(port=3000)
