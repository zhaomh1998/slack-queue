import os
import logging
from flask import Flask
from slack import WebClient
from slackeventsapi import SlackEventAdapter
import ssl as ssl_lib
import certifi


def get_app_home():
    return {
        "type": "home",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Hi David :wave:"
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
                        "value": "click_me_123"
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
                        "value": "click_me_123"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "emoji": True,
                            "text": "Pass to Other Tutor"
                        },
                        "style": "danger",
                        "value": "click_me_123"
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
                                   view=get_app_home())


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
    # Disregard own message
    if user_id == bot_user.data['user_id']:
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
        blocks=get_request_block()
#         text=f"""Hello! :tada:
# I received >>{text}<< from {user_id} on channel {channel_id}!
# Event type is {event.get("type")}
#         """
    )

    # slack_web_client.views_publish(user_id=user_id, view=get_request_block())


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())
    ssl_context = ssl_lib.create_default_context(cafile=certifi.where())
    app.run(port=3000)
