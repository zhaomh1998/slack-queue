from slack import WebClient
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
    def __init__(self, bot_token):
        # Initialize a Web API client
        # Note: Slack WebClient need to be in async mode in order to get two request at same time to work
        # https://github.com/slackapi/python-slackclient/issues/429
        self.slack_web_client = WebClient(token=bot_token)  # , run_async=True)
        self.bot_user = self.slack_web_client.auth_test()
        self.all_users = self.slack_web_client.users_list()
        self.id_to_name = dict()
        self.id_to_teamId = dict()

    def get_user_name(self, user_id):
        if user_id not in self.id_to_name.keys():
            self.id_to_name[user_id] = \
                self.slack_web_client.users_info(user=user_id).data['user']['profile']['display_name']
        return self.id_to_name[user_id]

    def get_user_teamid(self, user_id):
        if user_id not in self.id_to_teamId.keys():
            self.id_to_teamId[user_id] = self.slack_web_client.users_info(user=user_id).data['user']['team_id']
        return self.id_to_teamId[user_id]

    def get_channel_name(self, channel_id):
        channel_info = self.slack_web_client.conversations_info(channel=channel_id).data['channel']
        if channel_info['is_im']:
            im_with = channel_info['user']
            return f'Private Message with {self.get_user_name(im_with)}'
        else:
            return channel_info['name_normalized']

    def is_this_bot(self, user_id):
        return user_id == self.bot_user.data['user_id']

    def send_chat_text(self, channel_id, text):
        self.slack_web_client.chat_postMessage(channel=channel_id, text=text)
        return self

    def send_chat_block(self, channel_id, block):
        self.slack_web_client.chat_postMessage(channel=channel_id, blocks=block)
        return self

    def send_home_view(self, user_id, view):
        self.slack_web_client.views_publish(user_id=user_id, view=view)
        return self

    def send_modal(self, trigger_id, modal):
        self.slack_web_client.views_open(trigger_id=trigger_id, view=modal)
        return self

    def delete_chat(self, channel_id, msg_ts):
        self.slack_web_client.chat_delete(channel=channel_id, ts=msg_ts)
        return self

    def get_im_channel(self, user_id):
        return self.slack_web_client.conversations_open(users=[user_id])['channel']['id']

    def get_request_block(self, student_uid):
        student_name = self.get_user_name(student_uid)
        student_im = f'slack://user?team={self.get_user_teamid(student_uid)}&id={student_uid}'
        return [
            ui.text(f"You have a new request from {student_name}:\n*<{student_im}|Click to chat with {student_name} >*"),
            ui.text(f"*Question Brief:*\n<FIXME>"),
            ui.actions([ui.button_styled("Finished!", INTERACTION_TA_DONE, "primary"),
                        ui.button_styled("Pass to Other TA", INTERACTION_TA_PASS, "danger")])
        ]
