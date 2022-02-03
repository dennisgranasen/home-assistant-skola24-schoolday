"""
Get data from skola24
"""

import logging
import json
import requests
from datetime import datetime, timedelta

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.components.rest import RestData
from homeassistant.components.binary_sensor import PLATFORM_SCHEMA, BinarySensorEntity
from homeassistant.const import CONF_NAME

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME            = 'Skola24'
#DEFAULT_INTERVAL        = 86400 # once a day
#DEFAULT_INTERVAL        = 18000 # every five hours
HEADERS                 = {"X-Scope": "8a22163c-8662-4535-9050-bc5e1923df48", "Content-Type":"application/json"}
CONF_URL                = 'url'
CONF_SCHOOL             = 'school'
CONF_SSN                = 'pin'
CONF_CLASSNAME          = 'class'
CONF_SENSORNAME         = 'name'
CONF_OFFSET             = 'offset'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SCHOOL, default=0): cv.string,
    vol.Optional(CONF_CLASSNAME): cv.string,
    vol.Optional(CONF_SSN): cv.string,
    vol.Required(CONF_URL, default=0): cv.string,
    vol.Required(CONF_SENSORNAME, default=0): cv.string,
    vol.Optional(CONF_OFFSET, default=0): vol.Coerce(int)
})
#SCAN_INTERVAL = timedelta(minutes=DEFAULT_INTERVAL)

async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    await add_sensors(
        hass,
        config,
        async_add_devices,
        discovery_info
    )

async def add_sensors(
        hass,
        config,
        async_add_devices,
        discovery_info=None
    ):
    sensors = []
    er = entityRepresentation(hass, config)
    await er.loadData(hass)
    sensors.append(er)

    async_add_devices(sensors, True)

class schoolDay(): 
    def __init__(self, dayNumber, weekNumber):
        self._dayNumber = dayNumber
        self._weekNumber = weekNumber
        self._startTime = None
        self._endTime = None
    
    @property
    def dayNumber(self):
        return self._dayNumber

    @property
    def weekNumber(self):
        return self._weekNumber

    @property
    def startTime(self):
        return self._startTime

    @property
    def endTime(self):
        return self._endTime

    def addLesson(self,lesson):
        if self.startTime == None or self.startTime > lesson['timeStart']:
            self._startTime = lesson['timeStart']
        if self.endTime == None or self.endTime < lesson['timeEnd']:
            self._endTime = lesson['timeEnd']
    
    def __str__(self):
        return str(self.weekNumber) + ":" + str(self.dayNumber) + " " + self.startTime + " -> " + self.endTime

class entityRepresentation(BinarySensorEntity):
    def __init__(self, hass, config):
        self._name       = config.get(CONF_SENSORNAME)
        self._unit       = ""
        self._state      = "Unavailable"
        self._attributes = {}
        self.hass        = hass
        self._school     = config.get(CONF_SCHOOL)
        self._className  = config.get(CONF_CLASSNAME) if config.get(CONF_CLASSNAME) else None
        self._SSN        = config.get(CONF_SSN) if config.get(CONF_SSN) else None
        self._offset     = config.get(CONF_OFFSET)
        self._apiHost    = config.get(CONF_URL)
        self._schoolDays = []

        #self.entity_id = "skola24." + self._className

        weekNow   = datetime.today().isocalendar()[1]        
        #self.week = range(weekNow-1,weekNow+1)
        # To get the entire semester, use below
        if weekNow < 26: 
            self.week = range(weekNow,26)
        else:
            self.week = range(weekNow,52)
        self.year = (datetime.today() + timedelta(days=self._offset)).year

        self.selection = None

    @property
    def name(self):
        return self._name
        
    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return "_" + self._className

    @property
    def state(self):
        if self._state is not None:
            return self._state
        return None
        
    @property
    def is_on(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def unit_of_measurement(self):
        return self._unit

    @property
    def icon(self):
        return 'mdi:code'

    def errorCheck(self, r):
        if(r.status_code != requests.codes.ok):
            _LOGGER.error("[ERROR]\tGot response "+str(r.status_code)+" from "+r.url)
        if (r.json()["error"] != None):
            _LOGGER.error("[ERROR]\tGot the following error from "+r.url+" : "+ json.dumps(r.json()["error"]))
        if(r.json()["validation"]):
            _LOGGER.error("[ERROR]\tGot error from "+r.url+", error: "+json.dumps(r.json()["validation"]))
        if(r.json()["exception"] != None):
            _LOGGER.error("[ERROR]\tGot exception from "+r.url+", error: "+json.dumps(r.json()["exception"]))

    def makeRequest(self, url, data=None):
        if data is None:
            data="null"
        return requests.post(url, json=data, headers=HEADERS)

    async def loadData(self, hass): 
        guid = await self.getSchool(hass)
        if not self._SSN and not self._className:
            _LOGGER.error("[ERROR]\tYou must define one of SSN or ClassName")
        if self._SSN:
            selection = await self.getEncryptedSelection(hass, self._SSN)
            selectionTypeId = 4
        else:
            selection = await self.getClass(hass, guid)
            selectionTypeId = 0
        renderKey = await self.getRenderKey(hass)
        schedule = await self.getTimeTable(hass, renderKey, selection, selectionTypeId, guid)
        self._schoolDays = self.parse(schedule)

    async def getSchool(self, hass):
        match = None
        listOfSchools = []
        data = {
            "getTimetableViewerUnitsRequest": {
                "hostname": self._apiHost
            }
        }
        schools = await hass.async_add_executor_job(self.makeRequest,
            "https://web.skola24.se/api/services/skola24/get/timetable/viewer/units",
            data
        )
        self.errorCheck(schools)
        for s in schools.json()["data"]["getTimetableViewerUnitsResponse"]["units"]:
            listOfSchools.append(s["unitId"])
            if self._school == s["unitId"]:
                match=s["unitGuid"]

        if match:
            return match
        else:
            if len(listOfSchools) > 0:
                _LOGGER.error('Please provide one if following')
                for s in listOfSchools:
                    _LOGGER.error(s)
            exit("ERROR: could not match school")

    async def getClass(self, hass, guid):
        match = None
        listOfClasses = []
        data = {
            "hostname": self._apiHost,
            "unitGuid": guid,
            "filters": {
                "class": "true"
            }
        }
        classes = await hass.async_add_executor_job(self.makeRequest,
            "https://web.skola24.se/api/get/timetable/selection",
            data
        )
        self.errorCheck(classes)
        for c in classes.json()["data"]["classes"]:
            listOfClasses.append(c["groupName"])
            if self._className == c["groupName"]:
                match=c["groupGuid"]

        if match:
            return match
        else:
            if len(listOfClasses) > 0:
                _LOGGER.error('Please provide one of the following:')
                for c in listOfClasses:
                    _LOGGER.error(c)
            exit("ERROR: could not match class")

    async def getEncryptedSelection(self, hass, studentId):
        data = {
            "signature": studentId
        }
        response = await hass.async_add_executor_job(self.makeRequest,
                "https://web.skola24.se/api/encrypt/signature",
                data
        )
        self.errorCheck(response)
        return response.json()["data"]["signature"]

    async def getRenderKey(self, hass):
        response = await hass.async_add_executor_job(self.makeRequest,
                "https://web.skola24.se/api/get/timetable/render/key"
        )
        self.errorCheck(response)
        return response.json()["data"]["key"]

    async def getTimeTable(self, hass, renderKey,
                           selection, selectionTypeId, guid):
        lessons = []
        for w in self.week:
            data={
                "renderKey":renderKey,
                "host":self._apiHost,
                "unitGuid":guid,
                "startDate":"null",
                "endDate":"null",
                "scheduleDay":0,
                "blackAndWhite":"false",
                "width":1223,
                "height":550,
                "selectionType": selectionTypeId,
                "selection":selection,
                "showHeader":"false",
                "periodText":"",
                "week":w,
                "year":self.year,
                "privateFreeTextMode":"false",
                "privateSelectionMode":"null",
                "customerKey":""
            }
            response = await hass.async_add_executor_job(self.makeRequest,
                    "https://web.skola24.se/api/render/timetable",
                    data
            )
            self.errorCheck(response)
            responseJson = response.json()["data"]["lessonInfo"]
            if responseJson is not None:
                for lesson in responseJson:
                    lesson["weekOfYear"] = w
                    lessons.append(lesson)
        return lessons

    def parse(self, data):
        schoolDays = []
        currentDay = None
        for lesson in data:
            if currentDay == None or currentDay.dayNumber != lesson['dayOfWeekNumber'] or currentDay.weekNumber != lesson['weekOfYear']:
                currentDay = schoolDay(lesson['dayOfWeekNumber'],lesson['weekOfYear'])
                schoolDays.append(currentDay)
            currentDay.addLesson(lesson)

        return schoolDays

    def getDateTime(self, dow, time, week):
        return datetime.strftime(
            datetime.strptime(
                f"{self.year} {week} {dow} {time}",
                "%Y %W %w %H:%M:%S"
            ),
            "%Y%m%dT%H%M%S"
        )

    def checkSchoolDay(self):    
        d = (datetime.today() + timedelta(days=self._offset)).isocalendar()
        weekNow = d[1]
        dayNow = d[2]
        for day in self._schoolDays:
            if day.weekNumber == weekNow and day.dayNumber == dayNow: 
                return day
        return None

    async def async_update(self):
        schoolDay = self.checkSchoolDay()

        if schoolDay is None:
            start = None
            end = None
        else:
            start = schoolDay.startTime
            end = schoolDay.endTime
           
        self._state = schoolDay is not None
        self._attributes.update({'start': start, 'end': end})

