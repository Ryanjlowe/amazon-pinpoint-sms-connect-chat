import boto3
import os
import logging
import json
import time
from websocket import create_connection

chat = boto3.client('connectparticipant')
sfn = boto3.client('stepfunctions')
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

    for record in event['Records']:
        payload = json.loads(record['Sns']['Message'])

        participant = payload['originationNumber']
        sms_identity = payload['destinationNumber']
        message = payload['messageBody']

        if message.upper() == 'CHAT':

            start_response = connect.start_chat_contact(
                InstanceId=os.environ.get('CONNECT_INSTANCE_ID'),
                ContactFlowId=os.environ.get('CONNECT_CONTACT_FLOW_ID'),
                Attributes= {
                    "username": participant
                },
                ParticipantDetails= {
                    "DisplayName": participant
                }
            )

            logging.info(start_response)

            create_response = chat.create_participant_connection(
                Type=['WEBSOCKET','CONNECTION_CREDENTIALS'],
                ParticipantToken=start_response['ParticipantToken']
            )

            logging.info(create_response)

            ws = create_connection(create_response['Websocket']['Url'])
            ws.send('{"topic":"aws/subscribe","content":{"topics":["aws/chat"]}}')
            ws.close()
            logging.info('Closed: ' + create_response['Websocket']['Url'])

            put_record(participant, sms_identity, start_response['ContactId'], start_response['ParticipantToken'], create_response['ConnectionCredentials']['ConnectionToken'])

            response = sfn.start_execution(
                stateMachineArn=os.environ.get('STATE_MACHINE_ARN'),
                input=json.dumps({'phone_number': participant, 'sms_identity': sms_identity, 'start_position': 0, 'wait': 0})
            )

            logging.info(response)

        else:
            record = get_record(participant, sms_identity)

            logging.info('Found Record: ')
            logging.info(record)

            create_response = chat.create_participant_connection(
                Type=['WEBSOCKET','CONNECTION_CREDENTIALS'],
                ParticipantToken=record['participation_token']
            )

            logging.info(create_response)

            ws = create_connection(create_response['Websocket']['Url'])
            ws.send('{"topic":"aws/subscribe","content":{"topics":["aws/chat"]}}')
            ws.close()
            logging.info('Closed: ' + create_response['Websocket']['Url'])

            response = chat.send_message(
                ContentType='text/plain',
                Content=message,
                ConnectionToken=create_response['ConnectionCredentials']['ConnectionToken']
            )

            logging.info(create_response)

    return True

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
