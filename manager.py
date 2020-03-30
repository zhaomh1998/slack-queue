from api import Slack


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


class QueueManager:
    """
    TA:
    - Log on
    - Log off
    - Assign
    - Complete

    Student:
    - Log on
    - Request TA
    - Exit Queue
    -
    """

    def __init__(self, slack_web_client):
        assert isinstance(slack_web_client, Slack)
        self.free_ta = []
        self.busy_ta = []
        self.pairs = []
        self.student_queue = []
        self.tas = dict()
        self.student_status = dict()  # TODO: Refactor this into a class
        self.student_ta_connection = dict()
        self.slack = slack_web_client

    def ta_login(self, user_id):
        if user_id not in self.tas.keys():
            self.tas[user_id] = TA(user_id)

        the_ta = self.tas[user_id]

        # TA Log on
        if not the_ta.active:
            self.free_ta.append(the_ta)
            the_ta.toggle_active()
            check_student_queue()
        # TA Log off
        else:
            if the_ta in self.busy_ta:
                the_ta.complete()
                assert the_ta in self.busy_ta
                self.busy_ta.remove(the_ta)
            else:
                assert the_ta in self.free_ta
                self.free_ta.remove(the_ta)
            the_ta.toggle_active()

    def is_ta(self, user_id):
        return user_id in self.tas.keys()

    def get_queue_length(self):
        return len(self.student_queue)

    def get_ta_size(self):
        return len(self.free_ta) + len(self.busy_ta)

    def get_queue_position(self, user_id):
        assert user_id in self.student_queue
        return self.student_queue.index(user_id) + 1

    def get_student_status(self, user_id):
        if user_id not in self.student_status.keys():
            self.student_status[user_id] = 'idle'

        return self.student_status[user_id]

    def queue_move(self):
        assert len(self.free_ta) != 0
        if len(self.student_queue) != 0:
            # Dequeue student
            user_id = self.student_queue[0]
            self.student_queue.remove(user_id)

            self.student_status[user_id] = 'busy'
            assigned_ta = self.free_ta[0]
            slack_operation = assigned_ta.assign(user_id)
            self.busy_ta.append(assigned_ta)
            self.free_ta.remove(assigned_ta)
            return slack_operation
