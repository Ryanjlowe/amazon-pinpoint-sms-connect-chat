import boto3
import os
import logging
import json
import time
from websocket import create_connection

pinpoint = boto3.client('pinpoint')
chat = boto3.client('connectparticipant')
sfn = boto3.client('stepfunctions')
connect = boto3.client('connect')

def lambda_handler(event, context):
    global log_level
    log_level = str(os.environ.get('LOG_LEVEL')).upper()
    if log_level not in [
                              'DEBUG', 'INFO',
                              'WARNING', 'ERROR',
                              'CRITICAL'
                          ]:
        log_level = 'ERROR'
    logging.getLogger().setLevel(log_level)

    logging.info(event)

    for record in event['Records']:
        payload = json.loads(record['Sns']['Message'])

        participant = payload['originationNumber']
        message = payload['messageBody']

        if message.upper() == 'START CHAT':

            start_response = connect.start_chat_contact(
                InstanceId='681f0632-1c02-4daa-8927-8d6555993624',
                ContactFlowId='e48330d3-f351-4eea-9e06-789048754d7f',
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

            # create_response['ConnectionCredentials']['ConnectionToken']

            # response = chat.send_message(
            #     ContentType='text/plain',
            #     Content='{"topic":"aws/subscribe","content":{"topics":["aws/chat"]}}',
            #     ConnectionToken=create_response['ConnectionCredentials']['ConnectionToken']
            # )

            # logging.info(response)


            ws = create_connection(create_response['Websocket']['Url'])
            ws.send('{"topic":"aws/subscribe","content":{"topics":["aws/chat"]}}')
            ws.close()
            logging.info('Closed: ' + create_response['Websocket']['Url'])

            time.sleep(10)

            response = chat.get_transcript(
                ContactId=start_response['ContactId'],
                MaxResults=5,
                ConnectionToken=create_response['ConnectionCredentials']['ConnectionToken']
            )

            logging.info(response)
            content = ''
            startId = ''
            for t in response['Transcript']:
                if t['ContentType'] == 'text/plain':
                    content = content + t['Content']
                startId = t['Id']

            pinpoint.send_messages(
                ApplicationId='e5962d587efd4147be4d29b6368510d5',
                MessageRequest={
                    'Addresses': {
                        participant: {
                            'ChannelType': 'SMS'
                        }
                    },
                    'MessageConfiguration': {
                        'SMSMessage': {
                            'Body': content,
                            'OriginationNumber': '+18129934132'
                        }
                    }
                }
            )

            time.sleep(10)

            logging.info('STARTID: ' + startId)

            if startId:
                logging.info('ONE')
                response = chat.get_transcript(
                    ContactId=start_response['ContactId'],
                    MaxResults=5,
                    ScanDirection='FORWARD',
                    StartPosition = {
                        'MostRecent': len(response['Transcript']) +1
                    },
                    ConnectionToken=create_response['ConnectionCredentials']['ConnectionToken']
                )
            else:
                logging.info('TWO')
                response = chat.get_transcript(
                    ContactId=start_response['ContactId'],
                    MaxResults=5,
                    # ScanDirection='FORWARD',
                    # StartPosition = {
                    #     'Id': startId
                    # },
                    ConnectionToken=create_response['ConnectionCredentials']['ConnectionToken']
                )

            logging.info(response)

            content = ''
            for t in response['Transcript']:
                if t['ContentType'] == 'text/plain':
                    content = t['Content']
                    break

            pinpoint.send_messages(
                ApplicationId='e5962d587efd4147be4d29b6368510d5',
                MessageRequest={
                    'Addresses': {
                        participant: {
                            'ChannelType': 'SMS'
                        }
                    },
                    'MessageConfiguration': {
                        'SMSMessage': {
                            'Body': content,
                            'OriginationNumber': '+18129934132'
                        }
                    }
                }
            )


            # response = chat.send_message(
            #     ContentType='text/plain',
            #     Content='Yo yo yo!',
            #     ConnectionToken=create_response['ConnectionCredentials']['ConnectionToken']
            # )

            # logging.info(response)
