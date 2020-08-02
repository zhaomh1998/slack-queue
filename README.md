# slack-queue
Slack queue bot for requesting help from a list of people

## Server Configuration
### Environmental Variables
```bash
vim /etc/environment
```
Add following 
```bash
SLACK_BOT_TOKEN=xxxx-xxxxxxxxxxxxx-xxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx
IP_ADDR=xxx.xxx.xxx.xxx
SLACK_SIGNING_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SLACK_TA_PASSWD=xxxxxx
```
### Startup execution
```bash
crontab -e
```
Assuming this repo is at `/root/slack-queue`, which python is `/root/anaconda3/bin/python`, screen name is `slack-queue`

Add following to the end
```bash
@reboot /usr/bin/screen -dmS slack-queue bash -c 'cd /root/slack-queue; /root/anaconda3/bin/python bot.py; exec bash'
```
