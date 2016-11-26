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
        'version': '0.2',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }


# --------------- Functions that control the skill's behavior ------------------

def get_welcome_response(session):
    """ If we wanted to initialize the session to have some attributes we could add those here"""
    session_attributes = session.get('attributes', {})
    card_title = 'Welcome to GeneraList'

    if session_attributes['currentList']:
        speech_output = "Welcome back. Go to the next item in your {} list by saying 'next'. " \
                        "Repeat your current step by saying 'repeat'. " \
                        "Edit your list by saying 'edit'. " \
                        "Or you can say things like: " \
                        "'review', 'preview', 'load', or 'create'.".format(session_attributes['currentList'])
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


def get_help_response(session):
    """If the user asks for help, smartly determine what help they want by looking at their session values."""
    session_attributes = session.get('attributes')
    should_end_session = True

    if session_attributes['currentTask'] and 'PLAY' == session_attributes['currentTask']:
        speech_output = "You currently have a list playback session in progress. To hear the next item" \
                        "in your list, say: 'next'."
        if session_attributes['currentStep'] > '1':
            speech_output += "To go back to the previous item in your list, say 'previous'. "
        speech_output += "To stop playback so you can resume later, say: 'stop'. To stop and unload your " \
                         "list, say: 'cancel'. If you want to load a new list, say: 'Alexa, ask generalist " \
                         "to load' and then a list name. To create a new list, say: 'Alexa, ask generalist " \
                         "to create a new list'."
    elif session_attributes['currentTask'] and 'CREATE' == session_attributes['currentTask']:
        speech_output = "You are in the process of creating a list. To add a new item, say: 'Alexa, " \
                        "tell generalist to add item'. To finish editing your list and to save it for " \
                        "later, say: 'Alexa, tell generalist to stop'. To cancel your list and lose any " \
                        "saved progress say: 'Alexa, tell generalist cancel'."
    elif session_attributes['currentTask'] and 'EDIT' == session_attributes['currentTask']:
        speech_output = "You are in the process of creating a list. To add a new item, say: 'Alexa, " \
                        "tell generalist to add item'. To finish editing your list and to save it for " \
                        "later, say: 'Alexa, tell generalist to stop'."
    else:
        return get_welcome_response(session)

def handle_session_stop_request(session):
    card_title = 'Stop'
    should_end_session = True
    session_attributes = session.get('attributes', {})
    speech_output = ""
    reprompt_text = ""

    # If the session is in create or edit mode, update the list, and set the stored status accordingly
    # Also reset the session to
    if session_attributes['currentTask'] in ['CREATE', 'EDIT']:
        # Update the list to start at the first step when loaded.
        session_attributes['currentStep'] = '1'
        update_list(session=session)

        speech_output = "Your list {lst} has been saved. To access your list say: " \
                        "'Alexa, tell generalist to load {lst}".format(lst=session_attributes['currentList'])
        reprompt_text = ""

        # Clear out the stored session, but only if we're in create or edit mode
        session_attributes['currentTask'] = None
        session_attributes['currentList'] = None
        session_attributes['currentStep'] = None
        update_session(session=session)

    else:
        speech_output = "Goodbye."
        reprompt_text = ""

    return build_response(session_attributes={},
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def handle_session_cancel_request(session):
    # TODO smartly handle cancel requests.
    card_title = 'Session Ended'
    session_attributes = session.get('attributes', {})

    speech_output = ""
    reprompt_text = ""
    should_end_session = True

    # If in create mode, but NOT edit mode, delete the list.
    if session_attributes['currentTask'] == 'CREATE':
        lists_table = boto3.resource('dynamodb').Table(LISTS_TABLENAME)
        try:
            lists_table.delete_item(
                Key={'userId': session['user']['userId'],
                     'listName': session_attributes['listName']},
                ReturnValues='NONE'
            )
        except botocore.exceptions.ClientError as e:
            print("ERROR: {}".format(e.response))
            raise
        
    # Clear out the stored session
    session_attributes['currentTask'] = None
    session_attributes['currentList'] = None
    session_attributes['currentStep'] = None
    update_session(session=session)
    
    return build_response(session_attributes={},
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def create_list(intent, session):
    """Use the user id to create a new list. Tell the user to simply speak the steps. After each step,
    validate and ask if they want to add another step or stop. If the list already exists, just error out
    with a message that tells the user to modify a list instead."""
    card_title = intent['name']

    # Before creating a list, make sure the current list's session is stored
    update_list(session=session)

    # Now create a new list session
    session_attributes = session.get('attributes', {})
    session_attributes['currentTask'] = 'CREATE'
    session_attributes['currentStep'] = '0'
    session_attributes['currentList'] = None

    should_end_session = False

    if 'listName' in intent['slots'] and 'value' in intent['slots']['listName']:
        session_attributes['listName'] = intent['slots']['listName']['value']
        speech_output = "Creating a list named '{}'. " \
                        "Now say: 'Add item.".format(session_attributes['listName'])
        reprompt_text = "You can say: 'Add item,' " \
                        "or you can say something like: 'Add: Set oven to 300 degrees.'"
    else:
        speech_output = "What is the name of your list?"
        reprompt_text = "Please tell me the name of your list."

    return build_response(session_attributes=session_attributes,
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def add_item(intent, session):
    """Adds an item to the end of a list."""
    card_title = intent['name']
    session_attributes = session.get('attributes', {})

    if session_attributes['currentTask'] not in ['CREATE', 'EDIT']:
        # If not in create or edit mode, we can't add an item.
        should_end_session = True
        speech_output = "I can't add a task if you're not in 'create' or 'edit' modes. Please say: " \
                        "'Alexa, ask generalist to create a new list.' " \
                        "Or say: 'Alexa, ask generalist to edit,' and a list name."
        reprompt_text = ""
    elif 'Item' in intent['slots'] and 'value' not in intent['slots']['Item']:
        should_end_session = False
        speech_output = "Say: 'Add,' and the next item in the list. For example, say: 'Add preheat the oven" \
                        "to 300 degrees'."
        reprompt_text = "To add an item to the list, say: 'Add,' and the next item in the list."

    elif 'Item' in intent['slots'] and 'value' in intent['slots']['Item']:
        # If we are in create or edit mode. Add items to the session_attributes
        should_end_session = False
        currentStep = str(int(session_attributes['currentStep'] + 1))

        # Add it to the database
        lists_table = boto3.resource('dynamodb').Table(LISTS_TABLENAME)
        try:
            lists_table.update_item(
                Key={'userId': session['user']['userId'],
                     'listName': session_attributes['currentList']},
                UpdateExpression="set numberOfSteps = :ns, items.{} = :it".format(currentStep),
                ExpressionAttributeValues={
                    ':ns': session_attributes['currentStep'],
                    ':it': intent['slots']['Item']['value']
                },
                ReturnValues="NONE"
            )
        except botocore.exceptions.ClientError as e:
            print('ERROR: {}'.format(e.response))
            raise

        speech_output = "Adding '{}'. " \
                        "Say: 'Add,' and the next item in the list, " \
                        "or say: 'stop' or 'save' to save the list. " \
                        "To cancel and lose your work, say: 'cancel'.".format(
            intent['slots']['Item']['value'])
        reprompt_text = "To add another item say: 'Add,' and the next item in the list." \
                        "Otherwise say: 'stop' or 'save' to save your progress or 'cancel'" \
                        "discard your list."
    else:
        should_end_session = True
        speech_output = "I didn't understand you." \
                        "Say: 'Add,' and the next item in the list, " \
                        "or say: 'all done'."
        reprompt_text = ""

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

def load_session(session):
    """Use the current session's userId to load the stored session information"""
    userId = session['user']['userId']
    session_attributes = session.get('attributes', {})

    stored_session_table = boto3.resource('dynamodb').Table(SESSION_TABLENAME)

    try:
        response = stored_session_table.get_item(Key={'userId': userId})
    except botocore.exceptions.ClientError as e:
        print("ERROR: {}".format(e.response))
        return

    try:
        session_attributes['currentList'] = response['Item']['currentList']
        session_attributes['currentTask'] = response['Item']['currentTask']
        if response['Item']['currentTask'] in ['CREATE', 'EDIT']:
            session_attributes['currentStep'] = response['Item']['numberOfSteps']
        else:
            session_attributes['currentStep'] = response['Item']['currentStep']
    except KeyError:  # If either currentList or currentStep was not in the response
        session_attributes['currentList'] = None
        session_attributes['currentTask'] = None
        session_attributes['currentStep'] = None
    print("userId: {}\n"
          "Loaded: session_attributes = {}".format(userId, session_attributes))


def update_session(session):
    """Store the requested information in the StoredSession table."""
    session_attributes = session.get('attributes', {})
    stored_session_table = boto3.resource('dynamodb').Table(SESSION_TABLENAME)
    try:
        stored_session_table.update_item(
            Key={'userId': session['user']['userId']},
            UpdateExpression="set currentList = :l, currentTask = :t, currentStep = :s",
            ExpressionAttributeValues={
                ':l': session_attributes['currentList'],
                ':t': session_attributes['currentTask'],
                ':s': session_attributes['currentStep']
            },
            ReturnValues="NONE"
        )
    except botocore.exceptions.ClientError as e:
        print('ERROR: {}'.format(e.response))
        raise


def update_list(session):
    """Store the current session information into the list."""
    session_attributes = session.get('attributes', {})
    lists_table = boto3.resource('dynamodb').Table(LISTS_TABLENAME)

    try:
        lists_table.update_item(
            Key={'userId': session['user']['userId'],
                 'listName': session_attributes['currentList']},
            UpdateExpression="set currentStep = :c",
            ExpressionAttributeValues={
                ':c': session_attributes['currentStep']
            },
            ReturnValues="NONE"
        )
    except botocore.exceptions.ClientError as e:
        print('ERROR: {}'.format(e.response))
        raise


# --------------- Events ------------------

def on_session_started(session_started_request, session):
    """ Called when the session starts """
    print('on_session_started requestId={}, sessionId={}'.format(session_started_request['requestId'],
                                                                 session['sessionId']))
    load_session(session=session)


def on_launch(launch_request, session):
    """ Called when the user launches the skill without specifying what they want"""
    print('on_launch requestId={}, sessionId={}'.format(launch_request['requestId'], session['sessionId']))
    # Dispatch to your skill's launch
    return get_welcome_response(session=session)


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
    elif intent_name == 'AddItemIntent':
        return add_item(intent, session)
    elif intent_name == 'AMAZON.NextIntent':
        return get_next_item_from_list(intent, session)
    elif intent_name == 'AMAZON.HelpIntent':
        return get_help_response(session)
    elif intent_name == 'AMAZON.StopIntent':
        return handle_session_stop_request(session)
    elif intent_name == 'AMAZON.CancelIntent':
        return handle_session_cancel_request(session)
    else:
        raise ValueError('Invalid intent')


def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session.
    Is not called when the skill returns should_end_session=true"""
    print('on_session_ended requestId={}, sessionId={}'.format(session_ended_request['requestId'],
                                                               session['sessionId']))
    update_session(session=session)
