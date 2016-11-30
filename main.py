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

    print("***GET_WELCOME_RESPONSE, session: {}".format(session))

    if session_attributes['currentList'] != "NONE":
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
    card_title = "Welcome to GeneraList"
    reprompt_text = ""

    if session_attributes['currentTask'] == 'PLAY':
        speech_output = "You currently have a list playback session in progress. To hear the next item" \
                        "in your list, say: 'next'."
        if session_attributes['currentStep'] != 'NONE' and session_attributes['currentStep'] > '1':
            speech_output += "To go back to the previous item in your list, say 'previous'. "
        speech_output += "To stop playback so you can resume later, say: 'stop'. To stop and unload your " \
                         "list, say: 'cancel'. If you want to load a new list, say: 'ask generalist " \
                         "to load' and then a list name. To create a new list, say: 'ask generalist " \
                         "to create a new list'."
    elif session_attributes['currentTask'] == 'CREATE':
        speech_output = "You are in the process of creating a list. To add a new item, say: " \
                        "'tell generalist to add item'. To finish editing your list and to save it for " \
                        "later, say: 'tell generalist to stop'. To cancel your list and lose any " \
                        "saved progress say: 'tell generalist cancel'."
    elif session_attributes['currentTask'] == 'EDIT':
        speech_output = "You are in the process of creating a list. To add a new item, say: " \
                        "'tell generalist to add item'. To finish editing your list and to save it for " \
                        "later, say: 'tell generalist to stop'."
    else:
        return get_welcome_response(session=session)

    return build_response(session_attributes=session_attributes,
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def handle_save_intent(session):
    card_title = 'Save'
    should_end_session = True
    session_attributes = session.get('attributes', {})

    # If the session is in create or edit mode, update the list, and set the stored status accordingly
    if session_attributes['currentTask'] in ['CREATE', 'EDIT']:
        # Update the list to start at the first step when loaded.
        session['attributes']['currentStep'] = '0'
        update_list(session=session)

        speech_output = "Your list {lst} has been saved and loaded. " \
                        "Play it by saying: 'next'.".format(lst=session_attributes['currentList'])
        reprompt_text = ""

        # Take us out of create mode
        session['attributes']['currentTask'] = "PLAY"

        # Update the session information
        update_session(session=session)

    else:
        speech_output = "Nothing to save"
        reprompt_text = ""

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def handle_session_stop_request(session):
    card_title = 'Stop'
    should_end_session = True
    session_attributes = session.get('attributes', {})

    # If the session is in create or edit mode, update the list, and set the stored status accordingly
    if session_attributes['currentTask'] in ['CREATE', 'EDIT']:
        # Update the list to start at the first step when loaded.
        session['attributes']['currentStep'] = '0'
        update_list(session=session)

        speech_output = "Your list {lst} has been saved and loaded. " \
                        "Play it by saying: 'next'.".format(lst=session_attributes['currentList'])
        reprompt_text = ""

        # Take us out of create mode
        session['attributes']['currentTask'] = "PLAY"

        # Update the session information
        update_session(session=session)

    else:
        speech_output = "Goodbye."
        reprompt_text = ""

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def handle_session_cancel_request(session):
    # TODO smartly handle cancel requests.
    card_title = 'Canceled'
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
                     'listName': session_attributes['listName']}
            )
        except botocore.exceptions.ClientError as e:
            print("ERROR: {}".format(e.response))
            raise

    # Clear out the stored session
    session['attributes']['currentTask'] = "NONE"
    session['attributes']['currentList'] = "NONE"
    session['attributes']['currentStep'] = "NONE"
    update_session(session=session)

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def create_list(intent, session):
    """Use the user id to create a new list. Tell the user to simply speak the steps. After each step,
    validate and ask if they want to add another step or stop. If the list already exists, just error out
    with a message that tells the user to modify a list instead."""
    card_title = intent['name']

    if 'value' in intent['slots']['listName']:
        # First make sure we're not creating a list with the same name we're on
        if intent['slots']['listName']['value'] == session['attributes']['currentList']:
            speech_output = "You can't create a new list with the same name as one of your current lists. " \
                            "Either choose a new name or delete the list with the same name."
            reprompt_text = ""
            should_end_session = True
            return build_response(session_attributes=session['attributes'],
                                  speechlet_response=build_speechlet_response(title=card_title,
                                                                              output=speech_output,
                                                                              reprompt_text=reprompt_text,
                                                                              should_end_session=should_end_session))
        # Next try and load the list with the desired list name from the db
        # If the list exists, force the user to delete it before they can create a new one with the same name
        else:
            table = boto3.resource('dynamodb').Table(LISTS_TABLENAME)
            try:
                response = table.get_item(Key={
                    'userId': session['user']['userId'],
                    'listName': session['attributes']['currentList']
                })
            except botocore.exceptions.ClientError as e:
                print("ERROR: create_list database failure: {}".format(e.response))
                raise

            if 'Item' not in response:
                # Otherwise, set the session attributes accordingly and create the list
                session['attributes']['currentList'] = intent['slots']['listName']['value']
                session['attributes']['currentTask'] = 'CREATE'
                session['attributes']['currentStep'] = '0'
                session['attributes']['numberOfSteps'] = '0'
                session['attributes']['listItems'] = {}
                update_session(session=session)
                speech_output = "Creating a list named '{}'. " \
                                "Now say something like: " \
                                "'Add 4 large eggs.'".format(session['attributes']['currentList'])
                reprompt_text = "You can say: 'Add item,' " \
                                "or you can say something like: 'Add: Set oven to 300 degrees.'"
                should_end_session = False
            else:
                speech_output = "You can't create a new list with the same name as one of your current lists. " \
                                "Either choose a new name or delete the list with the same name."
                reprompt_text = ""
                should_end_session = True
                return build_response(session_attributes=session['attributes'],
                                      speechlet_response=build_speechlet_response(title=card_title,
                                                                                  output=speech_output,
                                                                                  reprompt_text=reprompt_text,
                                                                                  should_end_session=should_end_session))
    else:
        speech_output = "What do you want to name your list? Say 'create' and a list name."
        reprompt_text = "In order to create a list, you must name it. Say: 'create' and then a name. For " \
                        "example say, 'Create brownie recipe.'"
        should_end_session = False


    print("***END OF CREATE, session: {}".format(session))

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def edit_list(intent, session):
    """Edit a list (currently only supports adding to the list)."""
    card_title = "Edit the List"
    speech_output = "You can edit your list by saying: 'add' and then an item. Or say: 'save'."
    reprompt_text = "Say: 'add' and an item. Or say: 'save'."
    should_end_session = False

    session['attributes']['currentTask'] = 'EDIT'

    if 'value' in intent['slots']['listName'] and \
                    intent['slots']['listName']['value'] != session['attributes']['currentList']:
        table = boto3.resource('dynamodb').Table(LISTS_TABLENAME)
        try:
            response = table.get_item(Key={
                'userId': session['user']['userId'],
                'listName': intent['slots']['listName']['value']
            })
        except botocore.exceptions.ClientError as e:
            print("ERROR: edit_list database get_item failed: {}".format(e.response))
            raise
        else:
            session['attributes']['currentList'] = response['Item']['listName']
            session['attributes']['currentStep'] = response['Item']['numberOfSteps']
            session['attributes']['listItems'] = response['Item']['listItems']
            session['attributes']['numberOfSteps'] = response['Item']['numberOfSteps']
    else:
        session['attributes']['currentStep'] = session['attributes']['numberOfSteps']

    update_session(session=session)

    return build_response(session_attributes=session['attributes'],
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
                        "'tell generalist to create a new list.' " \
                        "Or say: 'ask generalist to edit,' and a list name."
        reprompt_text = ""
    elif 'Item' in intent['slots'] and 'value' not in intent['slots']['Item']:
        should_end_session = False
        speech_output = "Say: 'Add,' and the next item in the list."
        reprompt_text = "To add an item to the list, say: 'Add,' and the next item in the list. For " \
                        "example, you can say: 'Add, 1 teaspoon of salt.'"

    elif 'Item' in intent['slots'] and 'value' in intent['slots']['Item']:
        # If we are in create or edit mode. Add items to the session_attributes
        should_end_session = False
        session['attributes']['currentStep'] = curr_step = str(int(session_attributes['currentStep']) + 1)
        session['attributes']['numberOfSteps'] = curr_step
        session['attributes']['listItems'][curr_step] = intent['slots']['Item']['value']

        # Add it to the database
        update_list(session=session)

        speech_output = "Adding '{}'. " \
                        "Say: 'Add,' and the next item. " \
                        "Or say: 'save', ".format(intent['slots']['Item']['value'])
        reprompt_text = "To add another item say: 'Add,' and the next item in the list." \
                        "Otherwise say: 'stop' or 'save' to save your progress or 'cancel'" \
                        "discard your list."
    else:
        should_end_session = True
        speech_output = "I didn't understand you." \
                        "Say: 'Add,' and the next item in the list, " \
                        "or say: 'all done'."
        reprompt_text = ""

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def delete_list(intent, session):
    """Use the user id to delete an existing list. This removes all steps and progress and resets the
    session to be empty. This should require explicit confirmation."""
    card_title = "Delete List"
    userId = session['user']['userId']
    should_end_session = True
    reprompt_text = ""

    if 'value' in intent['slots']['listName']:
        listName = intent['slots']['listName']['value']
        speech_output = "I deleted your list, {}.".format(listName)
    elif session['attributes']['currentList'] != 'NONE':
        listName = session['attributes']['currentList']
        speech_output = "I deleted your list, {}.".format(listName)
    else:
        speech_output = "I'm not sure what list to delete. Say: 'delete' and then a list name."
        reprompt_text = "I need to know which list to delete. Say: 'delete' and then a list name."

    if listName == session['attributes']['currentList']:
        session['attributes']['currentList'] = 'NONE'
        session['attributes']['currentStep'] = '0'
        session['attributes']['currentTask'] = 'None'
        session['attributes']['numberOfSteps'] = '0'
        session['attributes']['listItems'] = {}

    table = boto3.resource('dynamodb').Table(LISTS_TABLENAME)
    try:
        response = table.delete_item(
            Key={
                'userId': userId,
                'listName': listName, },
            ReturnValues='ALL_OLD'
        )
    except botocore.exceptions.ClientError as e:
        print('ERROR reading from database: {}'.format(e.response))
        raise

    if 'attributes' not in response:
        speech_output = "I couldn't find a list named {} to delete".format(listName)

    update_session(session=session)

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def load_list(intent, session):
    """Use the user id as a key and try to load the requested list from the database. If the list does not
    exist, offer to create the list. If the list does exist, set the value of the current list in the
    database to the requested list and set the current page to 1. So maybe a tuple? How does dynamo
    database work? Can I load ('My instructions for whatever', 1)?

    The key takeaway is that this function persists a session by setting the state in the database. That's
    it. It's the responsibility of some other intent to actually execute the step (whatever that means)."""
    card_title = intent['name']
    session_attributes = session.get('attributes', {})
    should_end_session = False  # Let the user work with the list right away

    if 'value' in intent['slots']['listName']:
        # If trying to load a new list
        if session_attributes['currentList'] != intent['slots']['listName']['value']:
            lists_table = boto3.resource('dynamodb').Table(LISTS_TABLENAME)
            try:
                response = lists_table.get_item(Key={
                    'userId': session['user']['userId'],
                    'listName': intent['slots']['listName']['value']
                })
            except botocore.exceptions.ClientError as e:
                print("ERROR in LoadList: {}".format(e.response))
                speech_output = "There was a problem loading the list from the database."
                reprompt_text = ""
                should_end_session = True
            else:
                try:
                    session['attributes']['currentList'] = response['Item']['listName']
                    session['attributes']['currentStep'] = response['Item']['currentStep']
                    session['attributes']['currentTask'] = 'PLAY'
                    session['attributes']['listItems'] = response['Item']['listItems']
                    session['attributes']['numberOfSteps'] = response['Item']['numberOfSteps']

                    update_session(session=session)

                    speech_output = "I loaded your list: {}. " \
                                    "You can play your list by saying: " \
                                    "'tell generalist next'.".format(intent['slots']['listName']['value'])
                    reprompt_text = "To start playback, say: 'next'."
                except KeyError:  # List not found
                    speech_output = "I wasn't able to find the list {} " \
                                    "in the database".format(intent['slots']['listName']['value'])
                    reprompt_text = ""
                    should_end_session = True
        else:  # If trying to load list that is already loaded
            session['attributes']['currentTask'] = 'PLAY'
            speech_output = "Your list {} is already loaded. Say: 'next' to hear the next item in the " \
                            "list.".format(session_attributes['currentList'])
            reprompt_text = "To hear the next item say: 'next'."
    else:
        should_end_session = True
        speech_output = "When you ask to load a list, make sure to tell me the name of the list. For " \
                        "example, say: 'load brownie recipe'."
        reprompt_text = "To load a list, please say: 'load' followed by the list name. For example, " \
                        "you could say something like: 'load brownie recipe'."

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def get_next_item_from_list(session):
    """Use the user id to determine the current list and step. Then execute the corresponding step. For
    now, this should simply be reading out the steps. This should ultimately increment the counter and
    notify the user if it has reached the end of the list."""
    card_title = "Get Next Item"
    reprompt_text = ""

    # No list is currently loaded
    if 'currentList' not in session['attributes'] or session['attributes']['currentList'] == "NONE":
        speech_output = "You need to load a list before you can play it back. Say: 'load' and the name of " \
                        "a list. Or, if you haven't created a list yet, say: 'create' and the name of the " \
                        "list that you want to create."
        should_end_session = True
    # Reached the end of the currently loaded list
    elif session['attributes']['currentStep'] == session['attributes']['numberOfSteps']:
        speech_output = "You've reached the end of your list {}. Start over by saying: 'start over'."
        should_end_session = True
    else:  # Able to continue to the next item in the list
        session['attributes']['currentStep'] = curr_step = str(int(session['attributes']['currentStep']) + 1)
        next_item = session['attributes']['listItems'][curr_step]
        speech_output = "{}".format(next_item)
        should_end_session = False  # Make it easy to get the next step right away
        update_session(session=session)
        update_list(session=session)

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def handle_start_over_request(session):
    """If a list is loaded and mode is in play, then reset current step to 0 and let user know"""
    card_title = "Start Over"
    should_end_session = True
    reprompt_text = ""

    if session['attributes']['currentList'] == "NONE":
        speech_output = "You must load a list before I can restart."
    elif session['attributes']['currentTask'] in ['CREATE', 'EDIT']:
        speech_output = "You are in {} mode. Save your list by saying: 'save' or 'stop' before trying to " \
                        "start over".format(session['attributes']['currentTask'].lower())
    else:
        session['attributes']['currentStep'] = '0'
        update_session(session=session)
        speech_output = "Restarting."

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def peek_at_next_item_from_list(session):
    """Use the user id to determine the current list and step. Then execute the corresponding step. For
    now, this should simply be reading out the steps. This should NOT increment the counter. If there are
    no more steps, notify the user they are on the last item in the list. Consider skipping back several
    steps."""
    card_title = "Peek at Next Item"
    reprompt_text = ""

    # No list is currently loaded
    if 'currentList' not in session['attributes'] or session['attributes']['currentList'] == "NONE":
        speech_output = "You need to load a list before you can play it back. Say: 'load' and the name of " \
                        "a list. Or, if you haven't created a list yet, say: 'create' and the name of the " \
                        "list that you want to create."
        should_end_session = True
    # Reached the end of the currently loaded list
    elif session['attributes']['currentStep'] == session['attributes']['numberOfSteps']:
        speech_output = "You're at the end of your list."
        should_end_session = True
    else:  # Able to peek at the next item in the list
        curr_step = str(int(session['attributes']['currentStep']) + 1)
        next_item = session['attributes']['listItems'][curr_step]
        speech_output = "{}".format(next_item)
        should_end_session = False  # Make it easy to get the next step right away

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def get_prev_item_from_list(session):
    """Use the user id to determine the current list and step. First decrement the step number (this could
    handle a jump of more than one step). Then execute the current step. Should this increment the step
    again? Yes, probably so."""
    card_title = "Get Previous Item"
    reprompt_text = ""

    # No list is currently loaded
    if 'currentList' not in session['attributes'] or session['attributes']['currentList'] == "NONE":
        speech_output = "You need to load a list before you can play it back. Say: 'load' and the name of " \
                        "a list. Or, if you haven't created a list yet, say: 'create' and the name of the " \
                        "list that you want to create."
        should_end_session = True
    elif session['attributes']['currentStep'] == 'NONE':
        speech_output = ""
        should_end_session = True
    elif session['attributes']['currentStep'] < '2':
        session['attributes']['currentStep'] = '0'
        update_session(session=session)
        update_list(session=session)
        speech_output = "You're at the beginning of your list."
        should_end_session = True
    else:  # Able to continue to the next item in the list
        session['attributes']['currentStep'] = curr_step = str(int(session['attributes']['currentStep']) - 1)
        next_item = session['attributes']['listItems'][curr_step]
        speech_output = "{}".format(next_item)
        should_end_session = False  # Make it easy to get the next step right away
        update_session(session=session)
        update_list(session=session)

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


def review_previous_item_from_list(session):
    """Use the user id to determine the current list and step. Execute the step but don't change the
    current step number. This is kind of like a reminder. It's more like 'Hey, what was the last step?'
    instead of 'Go back to the next step."""
    card_title = "Review Previous Item"
    reprompt_text = ""

    # No list is currently loaded
    if 'currentList' not in session['attributes'] or session['attributes']['currentList'] == "NONE":
        speech_output = "You need to load a list before you can play it back. Say: 'load' and the name of " \
                        "a list. Or, if you haven't created a list yet, say: 'create' and the name of the " \
                        "list that you want to create."
        should_end_session = True
    elif session['attributes']['currentStep'] == 'NONE':
        speech_output = ""
        should_end_session = True
    elif session['attributes']['currentStep'] == '1':
        speech_output = "You're at the beginning of your list."
        should_end_session = True
    else:
        curr_step = str(int(session['attributes']['currentStep']) - 1)
        next_item = session['attributes']['listItems'][curr_step]
        speech_output = "{}".format(next_item)
        should_end_session = False  # Make it easy to get the next step right away

    return build_response(session_attributes=session['attributes'],
                          speechlet_response=build_speechlet_response(title=card_title,
                                                                      output=speech_output,
                                                                      reprompt_text=reprompt_text,
                                                                      should_end_session=should_end_session))


# --------------- Session Persistence ------------------

def load_session(session):
    """Use the current session's userId to load the stored session information"""
    userId = session['user']['userId']

    stored_session_table = boto3.resource('dynamodb').Table(SESSION_TABLENAME)

    try:
        response = stored_session_table.get_item(Key={'userId': userId})
    except botocore.exceptions.ClientError as e:
        print("ERROR: {}".format(e.response))
        return

    try:
        session['attributes'] = response['Item']['attributes']
    except KeyError:
        if 'attributes' not in session:
            session['attributes'] = {}
        session['attributes']['currentList'] = "NONE"
        session['attributes']['currentTask'] = "NONE"
        session['attributes']['currentStep'] = "NONE"
    print("userId: {}\n"
          "Loaded: session_attributes = {}".format(userId, session['attributes']))


def update_session(session):
    """Store the requested information in the StoredSession table."""
    session_attributes = session.get('attributes', {})
    stored_session_table = boto3.resource('dynamodb').Table(SESSION_TABLENAME)
    try:
        stored_session_table.put_item(
            Item={
                'userId': session['user']['userId'],
                'attributes': session_attributes
            }
        )
    except botocore.exceptions.ClientError as e:
        print('ERROR: {}'.format(e.response))
        raise


def update_list(session):
    """Store the current session information into the list."""
    session_attributes = session.get('attributes', {})
    print("***UPDATE LIST: session: {}".format(session))
    lists_table = boto3.resource('dynamodb').Table(LISTS_TABLENAME)

    try:
        lists_table.put_item(
            Item={'userId': session['user']['userId'],
                  'listName': session_attributes['currentList'],
                  'numberOfSteps': session_attributes['numberOfSteps'],
                  'currentStep': session_attributes['currentStep'],
                  'listItems': session_attributes['listItems']
                  }
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
    print("***ON_LAUNCH session: {}".format(session))
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
    elif intent_name == 'EditListIntent':
        return edit_list(intent, session)
    elif intent_name == 'AddItemIntent':
        return add_item(intent, session)
    elif intent_name == 'SaveIntent':
        return handle_save_intent(session)
    elif intent_name == 'AMAZON.NextIntent':
        return get_next_item_from_list(session)
    elif intent_name == 'AMAZON.PreviousIntent':
        return get_prev_item_from_list(session)
    elif intent_name == 'PeekIntent':
        return peek_at_next_item_from_list(session)
    elif intent_name == 'ReviewIntent':
        return review_previous_item_from_list(session)
    elif intent_name == 'AMAZON.HelpIntent':
        return get_help_response(session)
    elif intent_name == 'AMAZON.StopIntent':
        return handle_session_stop_request(session)
    elif intent_name == 'AMAZON.CancelIntent':
        return handle_session_cancel_request(session)
    elif intent_name == 'AMAZON.StartOverIntent':
        return handle_start_over_request(session)
    elif intent_name == 'DeleteIntent':
        return delete_list(intent, session)
    else:
        raise ValueError('Invalid intent')


def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session.
    Is not called when the skill returns should_end_session=true"""
    print('on_session_ended requestId={}, sessionId={}'.format(session_ended_request['requestId'],
                                                               session['sessionId']))
    update_list(session=session)
    update_session(session=session)
