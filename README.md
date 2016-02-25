# MicrosoftFindService
An API written in Python to enable a user to interact with their Windows devices in a convinient way, such as remotely playing a sound, locking, or locating a supported device.

---
Authenticating the Service
---
To intialize the service, call the constructor of the ```MicrosoftFindService``` class:
```
>>> from service import MicrosoftFindService
>>> mfservice = MicrosoftFindService('username@host.com', 'password')
```

---
Working with Devices
---
To access the devices on the account, see this example:
```
>>> service.devices[0].content['name']
'Kodeys-Phone'
>>> phone = service.devices[0]
```
Now that I know that the device at index zero is my phone, I can try to find it, play a sound on it or lock it.
```
>>> phone.location()
{'longitude': 51.542548712504719, 'latitude': 42.273322511904794, 'horizontalAccuracy': 71, 'timeStamp': '1456443187278'}
>>> phone.play_sound()
>>> phone.lost_device(123456, "5555555555", "My phone is lost!")
```

---
This Project
---
I am willing to continue to work on bug fixes and future development of this simple script as requested. I just really needed someway to easily find my phone (which I used to be able to do with the pyicloud project when I had an iPhone). Also, a lot of the ideas and front-end function names originated from the pyicloud project, so check it out!
