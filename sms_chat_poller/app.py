import boto3
import os
import logging
import json
import time
from websocket import create_connection

pinpoint = boto3.client('pinpoint')
chat = boto3.client('connectparticipant')
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
    wait = event['wait']
    new_wait = 0
    wait_ms = event['wait_ms'] if 'wait_ms' in event else 0.3
    new_wait_ms = 0.3
    last_id = event['last_id'] if 'last_id' in event else None
    new_last_id = last_id


    record = get_record(phone_number, sms_identity)

    create_response = chat.create_participant_connection(
        Type=['WEBSOCKET','CONNECTION_CREDENTIALS'],
        ParticipantToken=record['participation_token']
    )

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
            MaxResults=10,
            SortOrder='ASCENDING',
            StartPosition= {'MostRecent': 0} if last_id is None else {'Id': last_id},
            ConnectionToken=create_response['ConnectionCredentials']['ConnectionToken']
        )

        logging.info(response)

        for transcript in response['Transcript']:

            new_last_id = transcript['Id']

            if last_id == transcript['Id']:
                logging.info('Nothing new')
                new_wait_ms = wait_ms * 1.2
                new_wait = 2 if new_wait_ms == 0 else int(new_wait_ms)
                continue

            elif transcript['ContentType'] != 'text/plain':
                logging.info('Got Something Not Text')
                continue

            elif transcript['ParticipantRole'] == 'CUSTOMER':
                logging.info('Got Message from Customer')
                continue

            else:
                message = transcript['Content']
                logging.info('Got Message from Agent')

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

        return {
            'phone_number': phone_number,
            'sms_identity': sms_identity,
            'wait': new_wait,
            'wait_ms': new_wait_ms,
            'last_id': new_last_id
        }



def put_record(phone_number, sms_identity, contact_id, participation_token, connection_token):
    table.put_item(
        Item= {
            'phone_number': phone_number,
            'sms_identity': sms_identity,
            'contact_id': contact_id,
            'participation_token': participation_token,
            'connection_token': connection_token
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

def delete_record(phone_number, sms_identity):
    table.delete_item(
        Key={
            'phone_number': phone_number,
            'sms_identity': sms_identity
        }
    )
