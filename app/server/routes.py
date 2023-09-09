import json
from requests.exceptions import HTTPError

import allegro.disputes
import allegro.threads

import datastore.db_disputes
import datastore.db_threads

from flask import Flask, request, jsonify
from flask_restful import Api, Resource

import front.inboxes

import front.conversations

import webserver.parser

app = Flask(__name__)
api = Api(app)


class AttachmentsCountException(Exception):
    "Raised when webhook from Front contains more than one attachment."
    pass


class Front(Resource):
    def get(self):
        return jsonify({"message": "OK"})

    def post(self):
        try:
            print('----------------')
            print(request.get_data(as_text=True))
            print('----------------')
            print('NEW REQUEST RECEIVED!')
            print('Validation...', end=" ")
            validated_data = webserver.parser.validate_request(request)
            if not validated_data:
                print('FAILED!')
                return {"message": "Request validation failed"}, 400
            print('OK!', end=" ")

            data_text = validated_data["body_text"]
            signature = validated_data["signature"]

            print('Authentication...', end=" ")
            is_authenticated = webserver.parser.authenticate_signature(
                body=data_text, signature=signature)
            if not is_authenticated:
                print('FAILED!')
                return {"message": "Request authentication failed"}, 401
            print('OK!', end=" ")

            print('Parsing...', end=" ")
            parsed_data = webserver.parser.parse_request(data_text)
            if not parsed_data:
                return {"message": "Request parsing failed"}, 400
            print('OK!')

            if parsed_data["endpoint_type"] == "DYSKUSJA":
                if parsed_data["attachment"]:
                    parsed_data["attachment"]["id"] = allegro.disputes.upload_front_attachment(
                        parsed_data["attachment"], login=parsed_data["login"])

                # print('Posting dispute message with payload:')
                print(parsed_data)

                posted_message = allegro.disputes.post_to_dispute(parsed_data)
                posted_message['front_uid_webhook'] = parsed_data["front_uid"]

                if datastore.db_disputes.update_db_message(login=parsed_data["login"], dispute_id=parsed_data["thread_id"], message=posted_message) == parsed_data["front_uid"]:
                    print(
                        f'Message successfuly inserted to database with Front UID: {parsed_data["front_uid"]}')

                # if parsed_data["type"] == "END_REQUEST":
                #     comment_body = 'Wiadomość oraz prośba o zakończenie dyskusji przyjęta przez Allegro.'
                # else:
                #     comment_body = 'Wiadomość przyjęta przez Allegro.'

            if parsed_data["endpoint_type"] == "PYTANIE":
                if parsed_data["attachment"]:
                    parsed_data["attachment"]["id"] = allegro.threads.upload_front_attachment(
                        parsed_data["attachment"], login=parsed_data["login"])

                print(parsed_data)

                if parsed_data["thread_id"] is None:
                    posted_message = allegro.threads.post_new_thread(
                        parsed_data)
                else:
                    posted_message = allegro.threads.post_to_thread(
                        parsed_data)

                if not datastore.db_threads.insert_thread_message_into_db(posted_message, seller=parsed_data["login"], interlocutor=parsed_data["buyer"], message_front_uid=parsed_data["front_uid"]):
                    raise SystemExit(
                        "Inserting webhook message into threads database failed.")

                # comment_body = 'Wiadomość przyjęta przez Allegro'

                # front.conversations.comment_handler(
                #     parsed_data["conversation_id"], comment_body)
                return {"message": "accepted"}, 201

        except HTTPError as http_err:
            try:
                result = json.loads(http_err.response.text)
                comment_body = result["errors"][0]["userMessage"]
            except:
                comment_body = f'{http_err.response.status_code} {http_err.response.text}'
            try:
                conversation_id = parsed_data["conversation_id"]
                front.conversations.comment_handler(
                    conversation_id, comment_body)
            except:
                print(
                    'Failed to post error as Front comment.')

            return {"message": "HTTPError occured during handling the request"}, 400
        except ValueError as val_err:
            try:
                conversation_id = parsed_data["conversation_id"]
                front.conversations.comment_handler(
                    conversation_id, str(val_err))
            except:
                print(
                    'Failed to post error as Front comment.')

            return {"message": str(val_err), "error": "ValueError"}, 400

        # except KeyError as key_err:
        #     try:
        #         err_msg = f'Request is missing required key. {str(key_err)}'
        #         print(err_msg)
        #         post_comment(conversation_id,
        #                      body=key_err)
        #     except HTTPError as comment_err:
        #         print('Posting error as Front thread comment failed.')
        #         print(
        #             f'{comment_err.response.status_code} {comment_err.response.text}

        # except Exception as fatal_error:
        #     try:
        #         print('Fatal error processing request.')
        #         print('-----------------')
        #         print(fatal_error)
        #         print('-----------------')
        #         print(fatal_error.with_traceback)
        #         post_comment(conversation_id, body=str(fatal_error))
        #         return {"message": "Error processing request", "error": str(fatal_error)}, 500

        #     except HTTPError as front_err:
        #         print('Posting Allegro API call error in Front thread comment failed.')
        #         print(
        #             f'{front_err.response.status_code} {front_err.response.text}')
        #         return {"message": "Error processing request", "error": str(fatal_error)}, 500
        #     finally:
        #         raise SystemExit(
        #             'Processing request failed with unexpected error') from fatal_error


api.add_resource(Allegro, "/allegro")


@app.route('/healthcheck')
def healthcheck():
    return 'OK'


# if __name__ == '__main__':
#     serve(app, host='0.0.0.0', port=7998)
