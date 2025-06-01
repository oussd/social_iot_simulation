from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, time
import json
import os

@dataclass
class TimeParameters:
    simulation_duration_minutes: int
    working_hours_start: time
    working_hours_end: time
    time_zone: str

@dataclass
class ZoneConfig:
    zone_id: str
    zone_type: str  # office, meeting_room, lobby, etc.
    size_m2: float
    base_temperature: float
    occupancy_pattern: Dict[str, float]  # hour -> occupancy probability

@dataclass
class DeviceConfig:
    device_id: str
    device_type: str  # temperature_sensor, hvac_control, etc.
    zone_id: str
    update_interval_minutes: int
    capabilities: List[str]

@dataclass
class EnvironmentalConfig:
    base_temperature_range: tuple[float, float]
    weather_conditions: List[Dict[str, Any]]
    temperature_variation_per_hour: float
    window_effect_on_temperature: float

@dataclass
class EventProbabilities:
    window_open_probability: float
    access_event_probability: float
    emergency_event_probability: float
    device_failure_probability: float

@dataclass
class BuildingScenario:
    time_parameters: TimeParameters
    zones: List[ZoneConfig]
    devices: List[DeviceConfig]
    environmental_config: EnvironmentalConfig
    event_probabilities: EventProbabilities
    generated_events: List[Dict[str, Any]]
    timestamp: str  # When the scenario was generated

def save_scenario_to_json(scenario: BuildingScenario, filename: str):
    """Save a building scenario to a JSON file with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_with_timestamp = f"{filename}_{timestamp}.json"
    
    def convert_to_dict(obj):
        if isinstance(obj, (TimeParameters, ZoneConfig, DeviceConfig, 
                          EnvironmentalConfig, EventProbabilities, BuildingScenario)):
            return {k: convert_to_dict(v) for k, v in obj.__dict__.items()}
        elif isinstance(obj, time):
            return obj.strftime("%H:%M")
        elif isinstance(obj, (list, tuple)):
            return [convert_to_dict(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: convert_to_dict(v) for k, v in obj.items()}
        return obj

    scenario_dict = convert_to_dict(scenario)
    
    with open(filename_with_timestamp, 'w') as f:
        json.dump(scenario_dict, f, indent=2)
    
    return filename_with_timestamp

def load_scenario_from_json(filename: str) -> BuildingScenario:
    """Load a building scenario from a JSON file."""
    with open(filename, 'r') as f:
        data = json.load(f)
    
    def convert_time(time_str: str) -> time:
        hour, minute = map(int, time_str.split(':'))
        return time(hour, minute)
    
    # Convert the JSON data back to dataclass objects
    time_params = TimeParameters(
        simulation_duration_minutes=data['time_parameters']['simulation_duration_minutes'],
        working_hours_start=convert_time(data['time_parameters']['working_hours_start']),
        working_hours_end=convert_time(data['time_parameters']['working_hours_end']),
        time_zone=data['time_parameters']['time_zone']
    )
    
    zones = [ZoneConfig(**zone_data) for zone_data in data['zones']]
    devices = [DeviceConfig(**device_data) for device_data in data['devices']]
    
    env_config = EnvironmentalConfig(**data['environmental_config'])
    event_probs = EventProbabilities(**data['event_probabilities'])
    
    return BuildingScenario(
        time_parameters=time_params,
        zones=zones,
        devices=devices,
        environmental_config=env_config,
        event_probabilities=event_probs,
        generated_events=data['generated_events'],
        timestamp=data['timestamp']
    ) 