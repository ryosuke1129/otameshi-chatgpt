from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage
from boto3.dynamodb.conditions import Key, Attr
import boto3
import datetime
import json
import openai
import os

LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
OPENAI_ORGANIZATION = os.getenv('OPENAI_ORGANIZATION')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
table = boto3.resource('dynamodb').Table('otameshi-chatgpt')

def chat_completion(text, user_id):
    openai.organization = OPENAI_ORGANIZATION
    openai.api_key = OPENAI_API_KEY
    openai.Model.list()
    config = ''
    response = table.query(
        KeyConditionExpression=Key('user_id').eq(user_id)
    )
    items = response['Items']
    for item in items:
        config += item['user_content']+'\n'
        config += item['GPT_reply']+'\n----------\n'
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": config + text + '。'}]
        )
    return completion['choices'][0]['message']['content']

def db_del(user_id):
    response = table.query(
        KeyConditionExpression=Key('user_id').eq(user_id)
    )
    items = response['Items']
    key_names = [ x["AttributeName"] for x in table.key_schema ]
    delete_keys = [ { k:v for k,v in x.items() if k in key_names } for x in items ]
    with table.batch_writer() as batch:
        for key in delete_keys:
            batch.delete_item(Key = key)

def lambda_handler(event, context):
    message_id = str(json.loads(event['body'])['events'][0]['message']['id'])
    reply_token = json.loads(event['body'])['events'][0]['replyToken']
    user_id = json.loads(event['body'])['events'][0]['source']['userId']
    message = json.loads(event['body'])['events'][0]['message']['text']
    if not json.loads(event['body'])['events'][0]['message']['type'] == 'text':
        line_bot_api.reply_message(reply_token, TextSendMessage(text='テキストメッセージのみ受け付けています。'))
    if json.loads(event['body'])['events'][0]['message']['type'] == 'text':
        if message == '会話をリセット':
            db_del(user_id)
            line_bot_api.reply_message(reply_token, TextSendMessage(text='これまでの会話履歴を消去しました。'))
        else:
            try:
                reply_message = chat_completion(message, user_id)
                tzinfo = datetime.timezone(datetime.timedelta(hours=9))
                now = datetime.datetime.now(tzinfo)
                table.put_item(
                    Item={
                    'user_id': user_id,
                    'send_at': str(now),
                    'message_id': message_id,
                    'user_content': message,
                    'GPT_reply': reply_message,
                    'del_time': int(datetime.datetime.timestamp(datetime.datetime(now.year, now.month, now.day, 0, 0, 0, 0, tzinfo))+86400)
                    }
                )
                ok_json = {"isBase64Encoded": False,
                        "statusCode": 200,
                        "headers": {},
                        "body": ""}
                line_bot_api.reply_message(reply_token, TextSendMessage(text=reply_message))
                return ok_json
            except:
                error_json = {"isBase64Encoded": False,
                            "statusCode": 500,
                            "headers": {},
                            "body": "Error"}
                line_bot_api.reply_message(reply_token, TextSendMessage(text='エラーが発生しました。'))
                return error_json