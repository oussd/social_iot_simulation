import random
from datetime import datetime
from typing import Dict, List, Any
from .building_scenario_config import (
    BuildingScenario, TimeParameters, ZoneConfig, DeviceConfig,
    EnvironmentalConfig, EventProbabilities
)


class BuildingScenarioGenerator:
    def __init__(self,
                 time_parameters: TimeParameters,
                 zones: List[ZoneConfig],
                 devices: List[DeviceConfig],
                 environmental_config: EnvironmentalConfig,
                 event_probabilities: EventProbabilities):
        self.time_parameters = time_parameters
        self.zones = zones
        self.devices = devices
        self.environmental_config = environmental_config
        self.event_probabilities = event_probabilities
        self.generated_events: List[Dict[str, Any]] = []

    def generate_scenario(self) -> BuildingScenario:
        """Generate a complete building scenario with all events."""
        # Generate periodic events (temperature readings)
        self._generate_periodic_events()
        
        # Generate random events (window openings, access events)
        self._generate_random_events()
        
        # Generate time-based events (access control during working hours)
        self._generate_time_based_events()
        
        # Sort all events by timestamp
        self.generated_events.sort(key=lambda x: x["timestamp"])
        
        return BuildingScenario(
            time_parameters=self.time_parameters,
            zones=self.zones,
            devices=self.devices,
            environmental_config=self.environmental_config,
            event_probabilities=self.event_probabilities,
            generated_events=self.generated_events,
            timestamp=datetime.now().strftime("%Y%m%d_%H%M%S")
        )

    def _generate_periodic_events(self):
        """Generate periodic events like temperature readings."""
        for device in self.devices:
            if device.device_type == "temperature_sensor":
                current_time = 0
                while current_time < self.time_parameters.simulation_duration_minutes:
                    if current_time % device.update_interval_minutes == 0:
                        temperature = self._generate_temperature_reading(
                            device.zone_id,
                            current_time
                        )
                        self.generated_events.append({
                            "type": "temperature_reading",
                            "timestamp": current_time,
                            "device_id": device.device_id,
                            "zone_id": device.zone_id,
                            "value": temperature
                        })
                    current_time += 1

    def _generate_random_events(self):
        """Generate random events like window openings."""
        for zone in self.zones:
            current_time = 0
            while current_time < self.time_parameters.simulation_duration_minutes:
                # Window opening events
                if random.random() < self.event_probabilities.window_open_probability:
                    duration = random.randint(5, 30)  # Window open for 5-30 minutes
                    self.generated_events.append({
                        "type": "window_opened",
                        "timestamp": current_time,
                        "zone_id": zone.zone_id,
                        "duration_minutes": duration
                    })
                
                # Emergency events
                if random.random() < self.event_probabilities.emergency_event_probability:
                    self.generated_events.append({
                        "type": "emergency",
                        "timestamp": current_time,
                        "zone_id": zone.zone_id,
                        "emergency_type": random.choice(["fire", "intrusion", "flood"])
                    })
                
                current_time += 1

    def _generate_time_based_events(self):
        """Generate time-based events like access control during working hours."""
        working_start = self.time_parameters.working_hours_start.hour
        working_end = self.time_parameters.working_hours_end.hour
        
        for zone in self.zones:
            current_time = 0
            while current_time < self.time_parameters.simulation_duration_minutes:
                current_hour = (current_time // 60) % 24
                
                # Access events during working hours
                if working_start <= current_hour < working_end:
                    if random.random() < self.event_probabilities.access_event_probability:
                        self.generated_events.append({
                            "type": "access_entry",
                            "timestamp": current_time,
                            "zone_id": zone.zone_id,
                            "user_id": f"user_{random.randint(1, 100)}",
                            "access_type": random.choice(["entry", "exit"])
                        })
                
                current_time += 1

    def _generate_temperature_reading(self, zone_id: str, timestamp: int) -> float:
        """Generate a realistic temperature reading based on time and conditions."""
        zone = next(z for z in self.zones if z.zone_id == zone_id)
        base_temp = zone.base_temperature
        
        # Add time-based variation
        hour = (timestamp // 60) % 24
        # Peak at noon, lowest at midnight
        time_variation = self.environmental_config.temperature_variation_per_hour * (hour - 12) / 12
        
        # Add random variation
        random_variation = random.uniform(-0.5, 0.5)
        
        # Check for window open events affecting temperature
        window_effect = 0
        for event in self.generated_events:
            if (event["type"] == "window_opened" and 
                event["zone_id"] == zone_id and 
                timestamp - event["timestamp"] < event["duration_minutes"]):
                window_effect = self.environmental_config.window_effect_on_temperature
                break
        
        return base_temp + time_variation + random_variation + window_effect 