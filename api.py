from slack import WebClient
import sys
import hmac
import hashlib
import ui

INTERACTION_STUDENT_REFRESH = 'RefreshHomePage'
INTERACTION_STUDENT_CONNECT_TA = 'ConnectTA'
INTERACTION_STUDENT_DEQUEUE = 'DequeueConnectTA'
INTERACTION_STUDENT_END_CHAT = 'EndConnectTA'
INTERACTION_TA_LOGIN = 'TALogIn'
INTERACTION_TA_DONE = 'TADone'
INTERACTION_TA_PASS = 'TAPass'
INTERACTION_ADMIN_RESET = 'AdminReset'
INPUT_TA_PASS_ID = 'TAPassID'


class Slack:
    def __init__(self, bot_token, signing_secret):
        # Initialize a Web API client
        # Note: Slack WebClient need to be in async mode in order to get two request at same time to work
        # https://github.com/slackapi/python-slackclient/issues/429
        self.slack_web_client = WebClient(token=bot_token, run_async=True)
        slack_web_client_sync = WebClient(token=bot_token, run_async=False)  # TODO: Messy...
        self.bot_user = slack_web_client_sync.auth_test()
        self.all_users = slack_web_client_sync.users_list()
        self.id_to_name = dict()
        self.id_to_teamId = dict()
        self.signing_secret = signing_secret

    async def get_user_name(self, user_id):
        if user_id not in self.id_to_name.keys():
            self.id_to_name[user_id] = \
                (await self.slack_web_client.users_info(user=user_id)).data['user']['profile']['display_name']
        return self.id_to_name[user_id]

    async def get_user_teamid(self, user_id):
        if user_id not in self.id_to_teamId.keys():
            self.id_to_teamId[user_id] = (await self.slack_web_client.users_info(user=user_id)).data['user']['team_id']
        return self.id_to_teamId[user_id]

    async def get_channel_name(self, channel_id):
        channel_info = (await self.slack_web_client.conversations_info(channel=channel_id)).data['channel']
        if channel_info['is_im']:
            im_with = channel_info['user']
            return f'Private Message with {await self.get_user_name(im_with)}'
        else:
            return channel_info['name_normalized']

    def is_this_bot(self, user_id):
        return user_id == self.bot_user.data['user_id']

    async def send_chat_text(self, channel_id, text):
        await self.slack_web_client.chat_postMessage(channel=channel_id, text=text)
        return self

    async def send_chat_block(self, channel_id, block):
        await self.slack_web_client.chat_postMessage(channel=channel_id, blocks=block)
        return self

    async def send_home_view(self, user_id, view):
        await self.slack_web_client.views_publish(user_id=user_id, view=view)
        return self

    async def send_modal(self, trigger_id, modal):
        await self.slack_web_client.views_open(trigger_id=trigger_id, view=modal)
        return self

    async def delete_chat(self, channel_id, msg_ts):
        await self.slack_web_client.chat_delete(channel=channel_id, ts=msg_ts)
        return self

    async def get_im_channel(self, user_id):
        return (await self.slack_web_client.conversations_open(users=[user_id]))['channel']['id']

    async def get_request_block(self, student_uid):
        student_name = await self.get_user_name(student_uid)
        student_im = f'slack://user?team={await self.get_user_teamid(student_uid)}&id={student_uid}'
        return [
            ui.text(f"You have a new request from {student_name}:\n*<{student_im}|Click to chat with {student_name} >*"),
            # ui.text(f"*Question Brief:*\n<FIXME>"),
            ui.actions([ui.button_styled("Finished!", INTERACTION_TA_DONE, "primary")
                        # ui.button_styled("Pass to Other TA", INTERACTION_TA_PASS, "danger")
                        ])
        ]

    def verify_signature(self, timestamp, signature, data):
        # Verify the request signature of the request sent from Slack
        # Generate a new hash using the app's signing secret and request data

        # Compare the generated hash and incoming request signature
        # Python 2.7.6 doesn't support compare_digest
        # It's recommended to use Python 2.7.7+
        # noqa See https://docs.python.org/2/whatsnew/2.7.html#pep-466-network-security-enhancements-for-python-2-7
        if hasattr(hmac, "compare_digest"):
            req = str.encode('v0:' + str(timestamp) + ':') + data
            request_hash = 'v0=' + hmac.new(
                str.encode(self.signing_secret),
                req, hashlib.sha256
            ).hexdigest()
            # Compare byte strings for Python 2
            if (sys.version_info[0] == 2):
                return hmac.compare_digest(bytes(request_hash), bytes(signature))
            else:
                return hmac.compare_digest(request_hash, signature)
        else:
            # So, we'll compare the signatures explicitly
            req = str.encode('v0:' + str(timestamp) + ':') + data
            request_hash = 'v0=' + hmac.new(
                str.encode(self.signing_secret),
                req, hashlib.sha256
            ).hexdigest()

            if len(request_hash) != len(signature):
                return False
            result = 0
            if isinstance(request_hash, bytes) and isinstance(signature, bytes):
                for x, y in zip(request_hash, signature):
                    result |= x ^ y
            else:
                for x, y in zip(request_hash, signature):
                    result |= ord(x) ^ ord(y)
            return result == 0
