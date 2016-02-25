import dryscrape
import requests
from bs4 import BeautifulSoup

import threading
import time
import json

class MicrosoftFindService(object):
    """
    A service to log into a Microsoft Account and access Find My Phone
    """

    def __init__(self, username, password):
        """
        Create the service and log it in. 

        @params
        username : The username as it appears on a Microsoft Login Page.
        password : The password to authenticate the above user.

        @throws
        InvalidCredentialsException : Thrown if the given username or password is incorrect.
        """

        # log the user in 
        self.login({ 'username' : username, 'password' : password })

        # inialize the device manager
        self.device_manager = MicrosoftDeviceManager(self)    
        self.devices = self.get_devices()

    def login(self, credentials=None):
        """
        Log the given credentials in and authentication this service with cookies.

        @params
        credentials : Credentials used to log the user into a Microsoft Account.
                      By default, this will use the last used credentials (which may
                        be the credentials used to start the service).
                      This should contain both username and password keys.

        @throws
        InvalidCredentialsException : Thrown if the given credentials don't authenticate the session.
        """

        # load up the session and log the user in
        dryscrape.start_xvfb()
        session = dryscrape.Session()

        session.set_attribute('auto_load_images', False)
        session.visit('https://login.live.com/login.srf')

        if (not credentials): # if no new credentials were provided
            credentials = self.credentials
        else:
            self.credentials = credentials

        # enter the user's credentials into the login page
        session.at_css('#i0116').set(credentials['username'])
        session.at_css('#i0118').set(credentials['password'])

        session.at_css('#idSIButton9').click()

        # stupid trick to force the page to finish loading
        try:
            session.at_css('#FMht')
        except Exception:
            pass

        # make sure the login was succesful
        auth_cookies = {}

        # grab the authentication cookies from the session and save them for later
        for cookie in session.cookies():
            cookie_info = cookie.split(';')[0].split('=')
            if ('AMC' in cookie_info[0]):
                auth_cookies[cookie_info[0]] = cookie_info[1]

        if (not 'AMCSecAuth' in auth_cookies): # login was not sucessful
            raise InvalidCredentialsException(credentials['username'])
        
        self.auth_cookies = auth_cookies
        self.credentials = credentials

    def get_devices(self, attempts=5):
        """
        Load the list of devices from the Microsoft Account Devices page.
        
        @preconditions
        The current service must be authenticated.
        A device manager must be present in this service.

        @params
        attempts : Number of attempts to make to try to get the devices.
                   This means that self.login() will be called if the first attempt fails.

        @return
        A list of the devices and the currently known details about them.

        @throws
        InvalidCredentialsException : Thrown if credentials used to authenticate session are invalid.
        UnknownWebException : Thrown if something happens while trying to parse the devices.
        """

        # attempt to grab the devices page to parse
        to_attempt = lambda : requests.get('https://account.microsoft.com/devices', cookies=self.auth_cookies)
        successful = lambda result : \
                BeautifulSoup(result.text, 'html.parser').find_all('div', 'device-item-container')
        error_msg = 'Trying to parse devices for %s!' % self.credentials['username']

        response = BeautifulSoup(self.attempt(to_attempt, successful, attempts, error_msg).text, 'html.parser')           
        # the request was successful
        # parse information about the devices
        devices = []

        for device_div in response.find_all('div', 'device-item-container'): # proces each device
            content = {}

            # basic information
            content['id'] = device_div['data-deviceid']
            content['name'] = device_div.find('span', 'device-title').text
            content['deviceClass'] = device_div.find('img')['title'].split()[0]
            content['deviceModel'] = device_div.find('ul', 'device-base-properties').contents[3].text
            content['rawDeviceModel'] = device_div.find_all('li', 'mobile-hideshow')[-1].text

            # last seen location information
            last_seen_div = device_div.find('span', 'last-seen-container')

            content['location'] = {}

            if (last_seen_div): # if location is enabled
                content['locationEnabled'] = True
                content['location']['latitude'] = last_seen_div['data-latitude']
                content['location']['longitude'] = last_seen_div['data-longitude']
                content['location']['timeStamp'] = last_seen_div['data-timestamp']
                content['location']['horizontalAccuracy'] = last_seen_div['data-error-radius']
            else: # if location is not enabled
                content['locationEnabled'] = False

            # add the device to the running list
            devices.append(MicrosoftDevice(self.device_manager, content))

        return devices # return the list of devices

    def attempt(self, to_attempt, successful, attempts, error_msg):
        """
        Runs statement(s) until successful or attempts have run out. In between
        every attempt, a call to self.login() is made to make sure the session
        is authenticated.

        @params
        to_attempt : Statement(s) to be attempted. Should be passed in as a 
                     function or lambda that hasn't yet been evaluated!
        successful : Statement to determine if to_attempt was successful. Should
                     take one argument (return value of the to_attempt statements) and 
                     should return either True or False. Again, should not be evaluated
                     yet!
        attempts : The maximum number of times to attempt to run the given statements.
        error_msg : The error message to be used in the raising of the UnknownWebException
                    if all of the attempts fail. This should describe what was being done.

        @return
        Returns the successful result of running statement in to_attempt

        @throws
        InvalidCredentialsException : Thrown if credentials used to authenticate session are invalid.
        UnknownWebException : Thrown if none of the attempts to run to_attempt were successful.
        """
        # try the statement to be attempted
        result = to_attempt()

        # make sure that the statement was sucessful, or retry until attempts have run out
        while (not successful(result)):
            if (attempts > 0):
                self.login()
                attempts -= 1

                # try the command again
                result = to_attempt()
            else: # ran out of attempts
                raise UnknownWebException(result.text, error_msg)

        return result

    def run_command(self, command_name, device, attempts=5, **kwargs):
        """
        Runs a command, such as Find, Locate, or Ring, and includes the given key words.

        @params
        command_name : Commands supported by Microsoft's Device Service.
                       Supported commands are: Lock , Locate or Ring .
        device : Device to apply the command to. This function uses the device's id, so that 
                 must be set.
        attempts : Number of attempts to try to run the command (if previous attempts
                   are unsuccessful). A command is determined unsuccessful if the response
                   doesn't contain a 'CommandStatus' key.
        kwargs : Other key word arguments to be applied. An example is using 'Pin' : 1234 
                 when the Lock command is issued.

        @return
        The response from Microsoft to the command that was run, after being parsed as JSON
            data. It can be assumed that there will be a 'CommandStatus' key, because
            if there isn't an UnknownWebException would have been raised.

        @throws
        InvalidCredentialsException : Thrown if credentials used to authenticate session are invalid.
        UnknownWebException : Thrown if something happens while trying to parse the devices.
        """

        # set up the request headers
        headers = {
            'Host': 'account.microsoft.com',
            'Accept': 'application/json; q=0.01',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'MS-CV': 'kdRjDr7AO0SY5Cs/0.5.10.41',
        }
        
        # set up the url data information
        data = 'commandName=%s&deviceId=%s&jsonWebToken=&apiRequestValue=%s\
                &__RequestVerificationToken=XwY_ZBGHcYjX9vvtkDA-9amPKPRGdhFLC\
                A6r-9bNPLippwPcX3A_uMhgSW54W6CBlrk8IT-KtSL1h70Mvo4Y7c17fN0nxX\
                M6x0PucrpmMq81:Cqo9enbvzCpKmMGwF09apl7G0bbzliTZhuKV88v6_kVlUe\
                JouehvG-gbtLxTC126aPGQ-ybV8qeRwZwCsxsI2jDzggGFwcb0bvNY_qAAiCa\
                _Vo4ZyyQiGL1cRoA7U45F0' % (command_name, device.content['id'], json.dumps(kwargs))

        url = 'https://account.microsoft.com/devices/find/command'

        # attempt to make the request
        to_attempt = lambda : requests.post(url, headers=headers, cookies=self.auth_cookies, data=data)
        successful = lambda result : 'CommandStatus' in result.json()
        error_msg = 'Trying to send command %s for %s!' % (command_name, self.credentials['username'])

        response = self.attempt(to_attempt, successful, attempts, error_msg).json()

        # the response was successful
        return response       

    def command_status(self, command_id, device, attempts=5):
        """
        Check the status on a command already given for a specific device.

        @params
        command_id : The numeric id of the command that was issued. The id of
                     any given command is included in the response from running a command.
        device : The device that the command was run on. To check the status, the 
                 device must have an id field in its content.
        attempts : The number of attempts to check the command status.

        @return
        Returns the successful result of checking the status of the given command

        @throws
        InvalidCredentialsException : Thrown if credentials used to authenticate session are invalid.
        UnknownWebException : Thrown if none of the attempts to check the status are successful (or an
            invalid command_id or device was given).
        """

        # set up the request header
        headers = {
            'Host': 'account.microsoft.com',
            'Accept': 'application/json; q=0.01',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'MS-CV': 'kdRjDr7AO0SY5Cs0.5.10.41',
        }

        # set up the data for the status check
        data = 'commandId=%s&deviceId=%s' % (command_id, device.content['id'])

        # attempt to make the request
        to_attempt = lambda : \
                requests.get('https://account.microsoft.com/devices/find/status', \
                    headers=headers, cookies=self.auth_cookies, data=data)
        successful = lambda result : 'CommandStatus' in result.json()
        error_message = "Trying to check the status on a command run for %s" % device.content['name']

        response = self.attempt(to_attempt, successful, attempts, error_message).json()

        # the status check was successful
        return response

class MicrosoftDeviceManager(object):
    """
    Processes the actions and information associated a device.

    """

    def __init__(self, service):
        """
        Initialize the device manager.
        
        @params
        service : the MicrosoftFindService to run all device actions through.
        """
        # store the service for later use
        self.service = service

        # set up a command log to record currently running commands
        self.running_commands = {}

    def run_command(self, command, device, attempts=5, **kwargs):
        """
        Runs a command on a device with the given arguments. If a command of this
        type is already running on the device, no new command will be issued, and instead
        the status of the already running command will be returned. If the 
        last run command of this type is old, issues a new one as well.

        @params
        command : Command to run on the device. This is a string.
                  Possible values are: Locate , Ring or Lock .
        device : Device to run the command on. This devices's content dict must
                 contain its id in the key 'id' (used to run the command)
        attempts : Number of attempts to make to try to run the command. Default
                   is 5 times. In between each attempt, the session is attempted to 
                   be relogged-in.
        kwargs : Any arguments to be passed to the command. For example, a lock command
                 needs 'Pin' : '1234' or some other pin.

        @return
        The response of successfully running the command, OR, the current status of a command
            that is already running of the same type.

        @throws
        InvalidCredentialsException : Thrown if credentials used to authenticate session are invalid.
        UnknownWebException : Thrown if something erroneous happens while trying to run the command.
        """


        # determine if this command is already running
        if (command in self.running_commands[device.content['id']]):
            # update the status of the command to make sure it isn't old
            status = self.command_status(command, device)

            if (not status['TimedOut']): # the command isn't old, so return its status
                return status
        
            
        # determine whether SMS messages should be enabled to run the command
        if (device.is_phone()):
            kwargs['SmsAllowed'] = True
        else:
            kwargs['SmsAllowed'] = False

        # run the command
        command_info = self.service.run_command(command, device, attempts, **kwargs)

        # if the command was successful, add it to the list of running commands
        self.running_commands[device.content['id']][command] = command_info['CommandStatus']['CommandId']

        # and return the information from the request's responce
        return command_info

    def command_status(self, command, device, attempts=5):
        """
        Check the status on a command already run for a given device. This will return the
        status of the last run command of this type on the device.

        @params
        command : Command to check status of on the device. This is a string.
                  Possible values are: Locate , Ring or Lock .
        device : The device that the command was run on. To check the status, the
                 device must have an id field in its content.
        attempts : The number of attempts to check the command status.

        @return
        Returns the successful result of checking the status on the last run command of this type.

        @throws
        InvalidCredentialsException : Thrown if credentials used to authenticate session are invalid.
        UnknownWebException : Thrown if none of the attempts to check the status are successful (or an
            invalid command_id or device was given).
        NoRunningCommandException : Thrown if a command of the given type hasn't been run on this
            device durring the current session.
        """
        # make sure there is a running command
        if (not command in self.running_commands[device.content['id']]): # not run yet
            raise NoSuchRunningCommandException(self.running_commands[device.content['id']], command)

        # get the command id for the last run command          
        command_id = self.running_commands[device.content['id']][command]

        # check the status of the command
        command_status = self.service.command_status(command_id, device, attempts)

        # the command was successful
        return command_status


    def register_device(self, device):
        """
        Register the device with this manager. This just sets up the running_commands dictionary
        so that there are no key errors. Also runs sends a command to locate the device
        to try to improve the result of the next locate command.

        @params
        device : The device to register.
        """

        # add the device's id to the running commands dictionary
        self.running_commands[device.content['id']] = {}
        
        # locate the device
        
    def locate_device(self, device):
        """
        Locate the given device. This will use the current position of the last run command (if
        the command has finished recently) or will issue a new command to locate the device.
        This will update the device's information with currently known information!
        (It won't wait until a locate command has finished, the function should just be called
        until the full location has been determined).

        @params
        device : Device to find the location of. The device's location information will be
                 update with the most recent location information.

        @throws
        InvalidCredentialsException : Thrown if credentials used to authenticate session are invalid.
        UnknownWebException : Thrown if something erroneous happens while trying to find the location.
        """
        # run a locate command, which will return status of old command or status of a new command
        command_status = self.run_command('Locate', device)
        location = command_status['Location']

        # update the device info if the command has determined a location
        if (location):
            device.content['location']['latitude'] = location['Location']['Latitude']
            device.content['location']['longitude'] = location['Location']['Longitude']
            device.content['location']['horizontalAccuracy'] = location['Location']['ErrorRadius']
            device.content['location']['timeStamp'] = location['LastUpdatedTime'][6:-2]

            device.content['batteryLevel'] = location['BatteryLevel']

    def play_sound(self, device):
        """
        Play a sound on the given device. If a sound is already pending, no new action
            will be taken.

        @params
        device : The device to play a sound on.

        @throws
        InvalidCredentialsException : Thrown if credentials used to authenticate session are invalid.
        UnknownWebException : Thrown if something erroneous happens while trying to find the location.
        """
        # run a ring command, which will only execute if one isn't already pending
        self.run_command('Ring', device)

    def lock_device(self, device, pin, phone='',  message=""):
        """
        Lock the given device (if this is a valid command for the device).

        @params
        device : The device to lock.
        pin : The new pin to lock the device with.
        message : Message to lock the device with

        @throws
        InvalidCredentialsException : Thrown if credentials used to authenticate session are invalid.
        UnknownWebException : Thrown if something erroneous happens while trying to find the location.
        """
        kwargs = {}
        kwargs['Pin'] = pin
        kwargs['ContactPhoneNumber'] = phone
        kwargs['LockMessage'] = message
        self.run_command('Lock', device, **kwargs)

class MicrosoftDevice(object):
    """
    Represents a device from the Microsoft Find my Phone Service
    """

    def __init__(self, manager, content):
        """
        Inialize the device with the given information.

        @params
        manager : The device manager that this device will use to perform actions
                  or check statuses.
        content : The content that was parsed from the devices page.
        """
        # store the manager and content for later usage
        self.manager = manager
        self.content = content

        # register this device with the device manager
        self.manager.register_device(self)

    def location(self):
        """
        Locate the device. 

        @return
        Currently known information about the device's location.
        """
        # update the location of the device, if location is available
        self.manager.locate_device(self)
        
        return self.content['location'] 

    def status(self):
        """
        Get the device's currently known status.

        @return
        Currently known information about the device's location.
        """
        # collect some information about the status
        status = {}

        status['batteryLevel'] = self.content['batteryLevel']
        status['name'] = self.content['name']
        status['deviceDisplayName'] = self.content['deviceModel']
        
        return status

    def play_sound(self):
        """
        Play a sound on the device.
        """
        # ring the device
        self.manager.play_sound(self)

    def lost_device(self, pin, phone='', message="Find my Device"):
        """
        Lock the device with the given pin and message.

        @params
        phone : The phone number that the user can call.
        message : Message to display on the locked device.
        pin : Pin to lock the device with.
        """

        message = "Please contact %s %s" % (phone, message)
        self.manager.lock_device(self, pin, phone,  message)         

    def is_phone(self):
        if ('phone' in self.content['deviceClass'].lower()):
            return True
        else:
            return False        

"""
    EXCEPTIONS
"""
class InvalidCredentialsException(BaseException):
    """
    Thrown when the given credentials did not authenticate correctly with Microsoft Accounts
    """

    def __init__(self, username):
        """
        Creates the exception for invalid credentials.
        
        @params
        username : The username for the account that isn't authenticating in this instance.
        """
        self.username = username
        
        # instantiate the parent class
        super(InvalidCredentialsException, self).__init__(username)

class UnknownWebException(BaseException):
    """
    Thrown when some unknown web condition has caused the service to fail.
    """

    def __init__(self, response, message):
        """
        Creates the exception for an unknown exception.

        @params
        response : The response that was obtained from a request.
        message : Message explaining what the request was trying to do.
        """
        self.response = response
        self.message = message

        # instantiate the parent class
        super(UnknownWebException, self).__init__(response, message)

class NoSuchRunningCommandException(BaseException):
    """
    Thrown when the status of a command is looked up when there is no such command
        that has been run on the given device this session.
    """

    def __init__(self, running_commands, command):
        """
        Creates the exception for an no such running command exception.

        @params
        running_commands : The dictionary containing all of the commands running
                           for the devices.
        command : The name of the command that was looked up.
        """
        self.running_commands = running_commands
        self.command = command

        super(NoSuchRunningCommandException, self).__init__(running_commands, command)
