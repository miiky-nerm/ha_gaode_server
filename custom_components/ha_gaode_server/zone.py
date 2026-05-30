# -*- coding: utf-8 -*-
import logging
from homeassistant.components.http import HomeAssistantView

from aiohttp import web
import json
from json import JSONDecodeError
import os
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_ZONE,
)
from .const import (
    DEFAULT_ZONE_STORE_NAME,
    EVENT_NEW_STATE,
    CUSTOM_ATTR_GCJ02_LATITUDE,
    CUSTOM_ATTR_GCJ02_LONGITUDE,
)

_LOGGER = logging.getLogger(__name__)


class DxZone:
    """Hanlde zone"""

    gps_obj_list = {}
    zone_view_instance = None

    def __init__(self, hass, zone_view_instance):
        self.zone_view_instance = zone_view_instance
        self.hass = hass

    async def handle_zone_event(self, event):
        """Handle zone event"""
        data = event.data
        entity_id = data.get(ATTR_ENTITY_ID)
        new_state = data.get(EVENT_NEW_STATE)
        if new_state is None:
            # 被删除了不处理
            return
        attributes = new_state.attributes
        latitude = attributes.get(ATTR_LATITUDE)
        longitude = attributes.get(ATTR_LONGITUDE)
        gcj02_longitude = attributes.get(CUSTOM_ATTR_GCJ02_LONGITUDE)
        gcj02_latitude = attributes.get(CUSTOM_ATTR_GCJ02_LATITUDE)
        if gcj02_longitude and gcj02_latitude:
            _LOGGER.debug(
                "This zone have been set ---> entity_id: %s gcj02_latitude: %s gcj02_longitude: %s ",
                entity_id,
                str(gcj02_latitude),
                str(gcj02_longitude),
            )
        elif latitude and longitude:
            _LOGGER.debug(
                "Entity_id: %s latitude: %s longitude: %s",
                entity_id,
                str(latitude),
                str(longitude),
            )
            zone_view_instance = self.zone_view_instance
            file_data = await zone_view_instance.get_by_entity_id_in_file(entity_id)
            if file_data is not None:
                file_data = {
                    k: v
                    for k, v in file_data.items()
                    if k in ["gcj02_longitude", "gcj02_latitude", "dx_polygon"]
                }
                file_data[ATTR_ENTITY_ID] = entity_id
                await zone_view_instance.save(file_data)


class DxZoneView(HomeAssistantView):
    """Class for save or update zone"""

    url = "/api/dx/zone/save"
    name = "save zone entity"
    hass = None
    absolute_file_name = DEFAULT_ZONE_STORE_NAME

    def __init__(self, hass) -> None:
        self.hass = hass
        config_dir = hass.config.path()
        self.absolute_file_name = os.path.join(config_dir, DEFAULT_ZONE_STORE_NAME)

    def _load_saved_data_sync(self):
        """Load saved zone data from disk."""
        if not os.path.exists(self.absolute_file_name):
            return {}

        try:
            with open(self.absolute_file_name, "r", encoding="utf-8") as file:
                save_data = json.load(file)
                return save_data or {}
        except JSONDecodeError:
            _LOGGER.warning(
                "Zone store file %s is empty or invalid JSON, ignoring it",
                self.absolute_file_name,
            )
            return {}

    def _write_saved_data_sync(self, save_data):
        """Write saved zone data to disk."""
        tmp_file_name = f"{self.absolute_file_name}.tmp"
        with open(tmp_file_name, "w", encoding="utf-8") as file:
            json.dump(save_data, file)
        os.replace(tmp_file_name, self.absolute_file_name)

    async def _async_load_saved_data(self):
        return await self.hass.async_add_executor_job(self._load_saved_data_sync)

    async def _async_write_saved_data(self, save_data):
        return await self.hass.async_add_executor_job(
            self._write_saved_data_sync, save_data
        )

    async def post(self, request):
        """Handle POST request"""
        resp_json = await request.json()
        await self.save(resp_json)
        # entity_id = request.query.get("entity_id")
        # obj_list = self.gps_logger_instance.get_obj_list_by_entity_id(entity_id)
        return web.json_response({"msg": "ok"})

    async def get_by_entity_id_in_file(self, entity_id):
        """get saved data by entity_id"""
        save_data = await self._async_load_saved_data()
        return save_data.get(entity_id)

    async def save(self, data):
        """To save zone entity"""
        hass = self.hass
        entity_id = data.get(ATTR_ENTITY_ID)
        zone = hass.states.get(entity_id)

        save_data = await self._async_load_saved_data()
        if zone is not None:
            save_data[entity_id] = data
            await self._async_write_saved_data(save_data)
            clone_attributes = dict(zone.attributes)
            clone_attributes.update(data)
            self.hass.states.async_set(entity_id, zone.state, clone_attributes)

    async def load_all(self, event):
        """Load data from file and delete data if not exists"""
        hass = self.hass
        save_data = await self._async_load_saved_data()
        if not save_data:
            return

        new_save_data = {}
        zone_list = hass.states.async_all([CONF_ZONE])
        if len(zone_list) > 0:
            for zone in zone_list:
                attributes = zone.attributes
                entity_id = zone.entity_id
                if entity_id in save_data:
                    clone_attributes = dict(attributes)
                    now_data = save_data[entity_id]
                    clone_attributes.update(now_data)
                    new_save_data[entity_id] = now_data
                    self.hass.states.async_set(entity_id, 0, clone_attributes)
            await self._async_write_saved_data(new_save_data)
