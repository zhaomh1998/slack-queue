import os
import logging
from flask import Flask, request, make_response, Response
from slack import WebClient
from slackeventsapi import SlackEventAdapter
import ssl as ssl_lib
import certifi
import json

INTERACTION_STUDENT_CONNECT_TA = 'ConnectTA'
INTERACTION_TA_DONE = 'TADone'
INTERACTION_TA_PASS = 'TAPass'


def get_app_home(user_id):
    return {
        "type": "home",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Hi {get_user_name(user_id)} :wave:"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Great to see you here! App helps you to stay up-to-date with your meetings and events right here within Slack. These are just a few things which you will be able to do:"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "• Schedule meetings \n • Manage and update attendees \n • Get notified about changes of your meetings"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "But before you can do all these amazing things, we need you to connect your calendar to App. Simply click the button below:"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Connect to a Tutor / TA",
                            "emoji": True
                        },
                        "value": INTERACTION_STUDENT_CONNECT_TA
                    }
                ]
            }
        ]
    }


def get_request_block():
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "You have a new request from <studentName>:\n*<fakeLink.toEmployeeProfile.com|Click to chat with studentName>*"
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
                        "text": "Pass to Other Tutor"
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
    debug_print_msg(payload)


@slack_events_adapter.on("message")
def message(payload):
    event = payload.get("event", {})
    user_id = event.get("user")
    # Disregard message from None which could be a message-delete event
    # Disregard own message
    if user_id is None or user_id == bot_user.data['user_id']:
        return
    channel_id = event.get("channel")
    text = event.get("text")

    debug_print_msg(payload)


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
        blocks=get_request_block()
    )


# https://api.slack.com/messaging/interactivity
@app.route("/slack/interactive-endpoint", methods=["POST"])
def interactive_test():
    payload = json.loads(request.form["payload"])
    assert payload['type'] == 'block_actions'
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

    # Send an HTTP 200 response with empty body so Slack knows we're done here
    return make_response("", 200)


def get_user_name(user_id):
    return slack_web_client.users_info(user=user_id).data['user']['profile']['display_name']


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
