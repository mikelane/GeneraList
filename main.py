#!/usr/bin/env python

"""
GeneraList lets you use Amazon's Alexa to create and use lists that hold any type of data.

Ask GeneraList to store grocery items as you think of them during the week and then access those items when
you're on the go at the supermarket. Or give generalist a list of instructions that Alexa can read off to
you later as you ask her to. Have a recipe that you love? Let GeneraList read the instructions to you as
you're cooking.

To add: Music play lists, Video play lists, lists of slides for a slide show. These will require Alexa to
interact with other web services.
"""

from __future__ import print_function

import boto3
import botocore
import botocore.exceptions

__author__ = 'Mike Lane'
__email__ = 'mikelane@gmail.com'

# Set APP_ID to ensure only your skill calls this lambda handler
APP_ID = 'amzn1.ask.skill.e208302c-710b-4f30-9344-d0ae6ca3b774'
SKILL_NAME = 'GeneralList'
SKILL_INVOKE = 'generalist'
DB_REGION = 'us-east-1'
DB_URL = "https://dynamodb.{}.amazonaws.com".format(DB_REGION)

# Global session information
stored_session = {
    'current_list': None,
    'current_step': None
}
SESSION_TABLENAME = 'StoredSession'
LISTS_TABLENAME = 'Lists'


# --------------- Main handler ------------------

def lambda_handler(event, context):
    """Handles the Launch|Intent|SessionEnded request event
    Returns a JSON response to Alexa with:
    outputSpeech, reprompt, card, shouldEndSession"""

    if (event['session']['application']['applicationId']
            != 'amzn1.ask.skill.e208302c-710b-4f30-9344-d0ae6ca3b774'):
        if APP_ID != '':
            if event['session']['application']['applicationId'] != APP_ID:
                raise ValueError('Invalid Application ID',
                                 event['session']['application']['applicationId'],
                                 APP_ID)

    if event['session']['new']:
        on_session_started({'requestId': event['request']['requestId']}, event['session'])

    if event['request']['type'] == 'LaunchRequest':
        return on_launch(event['request'], event['session'])
    elif event['request']['type'] == 'IntentRequest':
        return on_intent(event['request'], event['session'])
    elif event['request']['type'] == 'SessionEndedRequest':
        return on_session_ended(event['request'], event['session'])


# --------------- Helpers that build all of the responses ----------------------

def build_speechlet_response(title, output, reprompt_text, should_end_session):
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'card': {
            'type': 'Simple',
            'title': 'SessionSpeechlet - ' + title,
            'content': 'SessionSpeechlet - ' + output
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text
            }
        },
        'shouldEndSession': should_end_session
    }


def build_response(session_attributes, speechlet_response):
    return {
        'version': '0.1',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }


# --------------- Functions that control the skill's behavior ------------------

def get_welcome_response():
    """ If we wanted to initialize the session to have some attributes we could add those here"""
    session_attributes = {}
    card_title = 'Welcome to GeneraList'

    if stored_session['current_list']:
        speech_output = "Welcome back. Go to the next item in your {} list by saying 'next'. " \
                        "Repeat your current step by saying 'repeat'. " \
                        "Edit your list by saying 'edit'. " \
                        "Or you can say things like: " \
                        "'review', 'preview', 'load', or 'create'.".format(stored_session['current_list'])
        reprompt_text = "To continue with your {} list say 'next', 'repeat', 'review', 'preview' or " \
                        "'edit'." \
                        "Say 'load' or 'create' to work with a different list."
    else:
        speech_output = "Welcome to generalist. Do you want to: 'load', 'create', or 'edit' a list?"
        reprompt_text = "Say: 'load', 'create', or 'edit'."

    should_end_session = False
    return build_response(session_attributes=session_attributes,
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def handle_session_end_request():
    card_title = 'Session Ended'
    speech_output = 'Goodbye.'
    # Setting this to true ends the session and exits the skill.
    should_end_session = True
    return build_response(session_attributes={},
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=None,
                                                                      should_end_session=should_end_session))


def create_list(intent, session):
    """Use the user id to create a new list. Tell the user to simply speak the steps. After each step,
    validate and ask if they want to add another step or stop. If the list already exists, just error out
    with a message that tells the user to modify a list instead."""
    card_title = intent['name']
    session_attributes = {}
    should_end_session = True  # TODO change this to false
    statuses = []
    reprompt_text = None

    speech_output = "I'm working on the {} feature.".format(card_title)  # TODO change this
    return build_response(session_attributes=session_attributes,
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


# TODO Finish this
def delete_list(intent, session):
    """Use the user id to delete an existing list. This removes all steps and progress and resets the
    session to be empty. This should require explicit confirmation."""
    return None


# TODO Finish this
def load_list(intent, session):
    """Use the user id as a key and try to load the requested list from the database. If the list does not
    exist, offer to create the list. If the list does exist, set the value of the current list in the
    database to the requested list and set the current page to 1. So maybe a tuple? How does dynamo
    database work? Can I load ('My instructions for whatever', 1)?

    The key takeaway is that this function persists a session by setting the state in the database. That's
    it. It's the responsibility of some other intent to actually execute the step (whatever that means)."""
    card_title = intent['name']
    session_attributes = {}
    should_end_session = True  # TODO change this to false
    statuses = []
    reprompt_text = None

    speech_output = "I'm working on the {} feature.".format(card_title)  # TODO change this
    return build_response(session_attributes=session_attributes,
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


# TODO Finish this
def get_next_item_from_list(intent, session):
    """Use the user id to determine the current list and step. Then execute the corresponding step. For
    now, this should simply be reading out the steps. This should ultimately increment the counter and
    notify the user if it has reached the end of the list."""
    return None


# TODO Finish this
def peek_at_next_item_from_list(intent, session):
    """Use the user id to determine the current list and step. Then execute the corresponding step. For
    now, this should simply be reading out the steps. This should NOT increment the counter. If there are
    no more steps, notify the user they are on the last item in the list. Consider skipping back several
    steps."""
    return None


# TODO Finish this
def get_prev_item_from_list(intent, session):
    """Use the user id to determine the current list and step. First decrement the step number (this could
    handle a jump of more than one step). Then execute the current step. Should this increment the step
    again? Yes, probably so."""
    return None


# TODO Finish this
def peek_at_prev_item_from_list(intent, session):
    """Use the user id to determine the current list and step. Execute the step but don't change the
    current step number. This is kind of like a reminder. It's more like 'Hey, what was the last step?'
    instead of 'Go back to the next step."""
    return None


# TODO Finish this
def stop(intent, sessions):
    """Stops the current read back, but keeps the information about the current step number and currently
    loaded list."""
    return None


# TODO Finish this
def cancel(intent, sessions):
    """Stops and resets the current list session and resets the current list session to be empty. This
    means that another list will have to be loaded before instructions can be executed."""
    return None


# --------------- Session Persistence ------------------

def load_session(curr_session):
    """Use the current session's userId to load the stored session information"""
    global stored_session  # global needed since we will modify stored_session
    userId = curr_session['user']['userId']
    StoredSessionTable = boto3.resource('dynamodb').Table(SESSION_TABLENAME)
    try:
        response = StoredSessionTable.get_item(Key={'userId': userId})
    except botocore.exceptions.ClientError as e:
        print("ERROR: {}".format(e.response))
        return

    if response:
        try:
            stored_session['current_list'] = response['Item']['currentList']
            stored_session['current_step'] = response['Item']['currentStep']
        except KeyError:  # If either currentList or currentStep was not in the response
            stored_session['current_list'] = None
            stored_session['current_step'] = None
        print("userId: {}\n"
              "Loaded: stored_session = {}".format(userId, stored_session))
    else:
        print('The load_session function got no response from the database.')


def store_session(curr_session, stored_session):
    """Store the requested information in the StoredSession table."""
    StoredSessionTable = boto3.resource('dynamodb').Table(SESSION_TABLENAME)
    try:
        response = StoredSessionTable.update_item(Key={
            'userId': curr_session['user']['userId'],
            'currentList': stored_session['currentList'],
            'currentStep': stored_session['currentStep']
        })
    except botocore.exceptions.ClientError as e:
        print('ERROR: {}'.format(e.response))


# --------------- Events ------------------

def on_session_started(session_started_request, session):
    """ Called when the session starts """
    print('on_session_started requestId={}, sessionId={}'.format(session_started_request['requestId'],
                                                                 session['sessionId']))
    load_session(curr_session=session)


def on_launch(launch_request, session):
    """ Called when the user launches the skill without specifying what they want"""
    print('on_launch requestId={}, sessionId={}'.format(launch_request['requestId'], session['sessionId']))
    # Dispatch to your skill's launch
    return get_welcome_response()


def on_intent(intent_request, session):
    """ Called when the user specifies an intent for this skill """
    print('on_intent requestId={}, sessionId={}'.format(intent_request['requestId'], session['sessionId']))

    intent = intent_request['intent']
    intent_name = intent_request['intent']['name']

    # Dispatch to your skill's intent handlers
    if intent_name == 'LoadListIntent':
        return load_list(intent, session)
    elif intent_name == 'CreateListIntent':
        return create_list(intent, session)
    elif intent_name == 'AMAZON.NextIntent':
        return get_next_item_from_list(intent, session)
    elif intent_name == 'AMAZON.HelpIntent':
        return get_welcome_response()
    elif intent_name == 'AMAZON.CancelIntent' or intent_name == 'AMAZON.StopIntent':
        return handle_session_end_request()
    else:
        raise ValueError('Invalid intent')


def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session.
    Is not called when the skill returns should_end_session=true"""
    print('on_session_ended requestId={}, sessionId={}'.format(session_ended_request['requestId'],
                                                               session['sessionId']))
    store_session(curr_session=session, stored_session=stored_session)
