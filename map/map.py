from __future__ import annotations
from typing import Optional, List
import aiohttp
import discord
import math
from time import time

from map.buttons import (EmptyButton, MultiplierButton, UpButton, LeftButton, DownButton,
                         RightButton, ZoomInButton, ZoomOutButton, SettingsButton)
from map.categories import CategorySelect
from map.map_objects import MapObject
from map.config import Area
from map.areaselect import AreaSelect
from config import MAP_SCALE, MAP_HEIGHT, MAP_WIDTH, TILESERVER, AREAS, STYLES


class Map(discord.ui.View):
    zoom: float
    lat: float
    lon: float
    style: str = STYLES[0][1]
    style_name: str = STYLES[0][0]
    multiplier: float
    marker_multiplier: float
    author_id: int
    url: str = TILESERVER + "staticmap"
    message: discord.Message
    embed: discord.Embed
    start: float

    width: int = MAP_WIDTH
    height: int = MAP_HEIGHT
    scale: int = MAP_SCALE
    category: CategorySelect
    map_objects: List[MapObject]

    def __init__(self, author_id: int):
        super().__init__(timeout=None)
        self.start = time()
        init_area = AREAS[0]
        self.zoom = init_area.zoom
        self.lat = init_area.lat
        self.lon = init_area.lon
        self.author_id = author_id

        self.multiplier = 1
        self.marker_multiplier = 1
        self.embed = discord.Embed()
        self.map_objects = []
        self.category = CategorySelect(self)

        for item in [
            self.category,
            AreaSelect(self),
            EmptyButton(0), UpButton(self), EmptyButton(1), ZoomInButton(self), MultiplierButton(self),
            LeftButton(self), DownButton(self), RightButton(self), ZoomOutButton(self), SettingsButton(self)
        ]:
            self.add_item(item)

    def get_data(self):
        data = {
            "style": self.style,
            "latitude": self.lat,
            "longitude": self.lon,
            "zoom": self.zoom,
            "width": self.width,
            "height": self.height,
            "format": "png",
            "scale": self.scale
        }
        if self.map_objects:
            markers = []
            for map_object in self.map_objects:
                markers += map_object.get_markers()
            data.update({
                "markers": markers
            })
        return data

    async def start_load(self):
        self.start = time()
        self.embed.set_footer(icon_url="https://cdn.discordapp.com/attachments/"
                                       "523253670700122144/881302405826887760/785.gif",
                              text="Loading...")
        await self.edit()

    def is_author(self, check_id: int):
        return check_id == self.author_id

    def point_to_lat(self, wanted_points):
        # copied from https://help.openstreetmap.org/questions/75611/transform-xy-pixel-values-into-lat-and-long
        C = (256 / (2 * math.pi)) * 2 ** self.zoom

        xcenter = C * (math.radians(self.lon) + math.pi)
        ycenter = C * (math.pi - math.log(math.tan((math.pi / 4) + math.radians(self.lat) / 2)))

        xpoint = xcenter - (self.width / 2 - wanted_points[0])
        ypoint = ycenter - (self.height / 2 - wanted_points[1])

        C = (256 / (2 * math.pi)) * 2 ** self.zoom
        M = (xpoint / C) - math.pi
        N = -(ypoint / C) + math.pi

        fin_lon = math.degrees(M)
        fin_lat = math.degrees((math.atan(math.e ** N) - (math.pi / 4)) * 2)

        return fin_lat, fin_lon

    def get_bbox(self):
        lat1, lon1 = self.point_to_lat(wanted_points=(0, 0))
        lat2, lon2 = self.point_to_lat(wanted_points=(self.width, self.height))
        lats = [lat1, lat2]
        lons = [lon1, lon2]
        return [min(lats), min(lons), max(lats), max(lons)]

    def get_resolution(self) -> float:
        resolution = 156543.03 * math.cos(math.radians(self.lat)) / (math.pow(2, self.zoom))
        return resolution

    def get_marker_size(self, size: int = 20) -> int:
        result = size * (math.pow(2, self.zoom))
        end_size = int(result // 50000)
        min_size = int((self.width * size) // 500)
        return max(end_size, min_size)

    @staticmethod
    def _get_meters() -> float:
        earth = 6373.0
        meters = 40 * ((1 / ((2 * math.pi / 360) * earth)) / 1000)  # meter in degree * 40
        return meters

    def get_lat_offset(self) -> float:
        meters = self._get_meters()
        resolution = self.get_resolution()
        return meters * resolution * self.multiplier

    def get_lon_offset(self) -> float:
        meters = self._get_meters()
        resolution = self.get_resolution()
        return (meters / math.cos((math.pi / 180))) * resolution * self.multiplier

    def jump_to_area(self, area: Area):
        self.lat = area.lat
        self.lon = area.lon
        self.zoom = area.zoom

    async def set_map(self):
        async with aiohttp.ClientSession() as session:
            async with session.post(self.url + "?pregenerate=true", json=self.get_data()) as resp:
                pregen_id = await resp.text()
                self.embed.set_image(url=self.url + "/pregenerated/" + pregen_id)
                self.embed.set_footer(text=f"This took {round(time() - self.start, 3)}s")

    async def edit(self):
        await self.message.edit(embed=self.embed, view=self)

    async def send(self, ctx):
        await self.set_map()
        self.message = await ctx.send(embed=self.embed, view=self)

    async def update(self):
        self.map_objects = []
        for selected_index in self.category.values:
            category = self.category.categories[int(selected_index)]

            bbox = self.get_bbox()
            new_objects = await category.get_map_objects(bbox)
            # TODO no duplicate IDs
            self.map_objects += new_objects

        self.map_objects = sorted(self.map_objects, key=lambda o: o.lat, reverse=True)

        await self.set_map()
        await self.edit()
