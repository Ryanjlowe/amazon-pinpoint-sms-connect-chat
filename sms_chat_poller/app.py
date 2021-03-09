import boto3
import os
import logging
import json
import time
from websocket import create_connection

pinpoint = boto3.client('pinpoint')
chat = boto3.client('connectparticipant')
connect = boto3.client('connect')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('sms-chat-history')


def lambda_handler(event, context):
    global log_level
    log_level = str(os.environ.get('LOG_LEVEL')).upper()
    if log_level not in [
                              'DEBUG', 'INFO',
                              'WARNING', 'ERROR',
                              'CRITICAL'
                          ]:
        log_level = 'INFO'
    logging.getLogger().setLevel(log_level)

    logging.info(event)

    phone_number = event['phone_number']
    sms_identity = event['sms_identity']
    last_id = event['last_id'] if 'last_id' in event else None
    new_last_id = last_id
    chat_ended = event['chat_ended'] if 'chat_ended' in event else False


    record = get_record(phone_number, sms_identity)

    create_response = chat.create_participant_connection(
        Type=['WEBSOCKET','CONNECTION_CREDENTIALS'],
        ParticipantToken=record['participation_token']
    )
    connection_token = create_response['ConnectionCredentials']['ConnectionToken']

    logging.info(create_response)

    ws = create_connection(create_response['Websocket']['Url'])
    ws.send('{"topic":"aws/subscribe","content":{"topics":["aws/chat"]}}')
    ws.close()
    logging.info('Closed: ' + create_response['Websocket']['Url'])

    cnt = 0
    while True:
        cnt = cnt + 1
        response = chat.get_transcript(
            ContactId=record['contact_id'],
            MaxResults=15,
            SortOrder='ASCENDING',
            StartPosition= {'MostRecent': 0} if last_id is None else {'Id': last_id},
            ConnectionToken=connection_token
        )

        logging.info(response)

        for transcript in response['Transcript']:

            new_last_id = transcript['Id']

            if last_id == transcript['Id']:
                logging.info('Nothing new')
                continue

            elif transcript['ContentType'] == 'application/vnd.amazonaws.connect.event.participant.left':
                logging.info('Agent left chat, disconnecting session')
                message = 'The agent has disconnected.  To start a new chat, reply with keyword "Chat".'
                send_response(phone_number, message, sms_identity)

                response = chat.disconnect_participant(
                    ConnectionToken=connection_token
                )
                stop_response = connect.stop_contact(
                    ContactId=record['contact_id'],
                    InstanceId=os.environ.get('CONNECT_INSTANCE_ID')
                )

                logging.info('Disconnect End User from Chat')
                logging.info(response)
                logging.info(stop_response)
                chat_ended = True
                break

            elif transcript['ContentType'] != 'text/plain':
                logging.info('Got Something Not Text')
                continue

            elif transcript['ParticipantRole'] == 'CUSTOMER':
                logging.info('Got Message from Customer')
                continue

            else:
                message = transcript['Content']
                logging.info('Got Message from Agent')
                send_response(phone_number, message, sms_identity)


        return {
            'chat_ended': chat_ended,
            'phone_number': phone_number,
            'sms_identity': sms_identity,
            'last_id': new_last_id
        }


def send_response(phone_number, message, sms_identity):
    pinpoint.send_messages(
        ApplicationId=os.environ.get('PINPOINT_PROJECT_ID'),
        MessageRequest={
            'Addresses': {
                phone_number: {
                    'ChannelType': 'SMS'
                }
            },
            'MessageConfiguration': {
                'SMSMessage': {
                    'Body': message,
                    'OriginationNumber': sms_identity
                }
            }
        }
    )


def get_record(phone_number, sms_identity):
    response = table.get_item(
        Key={
            'phone_number': phone_number,
            'sms_identity': sms_identity
        }
    )
    return response['Item']
