import logging
import time # Used for timestamp in log messages and filename
import os
from typing import Dict, Any # Changed List to Any for metrics flexibility

class SimulationLogger:
    _instance = None
    _initialized = False # To ensure _initialize_logger runs only once per instance logic

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SimulationLogger, cls).__new__(cls)
        return cls._instance

    def __init__(self, simulation_name: str = "SimLog", log_to_console: bool = True, log_to_file: bool = True):
        # This init can be called multiple times by different parts if not careful with singleton access.
        # The _initialized flag ensures core setup happens once.
        if self._initialized and hasattr(self, 'simulation_name') and self.simulation_name == simulation_name:
            return # Already initialized with the same name, do nothing

        self.simulation_name = simulation_name # Overall name for this logger instance (e.g., "lab" or "building")
        self.log_file_base = "simulation_run" # Base for log file names
        
        # Core logger setup
        self.logger = logging.getLogger(f"SIoT_Sim_{simulation_name}_{id(self)}") # Unique logger name
        self.logger.handlers = [] # Clear existing handlers if any (important for re-init scenarios or testing)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False # Prevent duplicate messages if root logger is configured

        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        # Formatter
        formatter = logging.Formatter('%(asctime)s [%(levelname)-5s] [%(sim_context)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        if log_to_file:
            # File handler with a unique name for this logger instance
            current_timestamp = time.strftime('%Y%m%d_%H%M%S')
            # Use self.simulation_name for the log file to group logs from the same comparison set
            log_filename = f"logs/{self.log_file_base}_{self.simulation_name}_{current_timestamp}.log"
            file_handler = logging.FileHandler(log_filename, mode='w') # 'w' to overwrite for each new logger instance
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        if log_to_console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        self.simulation_metrics: Dict[str, Dict[str, Any]] = {} # Stores metrics from different runs
        
        if not self.logger.handlers: # If no handlers were added (e.g. both console and file are false)
            self.logger.addHandler(logging.NullHandler()) # Avoid "No handlers could be found" warnings

        self._initialized = True
        self.log_info("LOGGER_INIT", f"Logger initialized for overall simulation: {self.simulation_name}", context_override=self.simulation_name)

    def _log_with_context(self, level, message, context):
        """Internal log method that uses extra for sim_context."""
        extra_dict = {'sim_context': context}
        self.logger.log(level, message, extra=extra_dict)

    def log_event(self, context_tag: str, message: str, level: str = 'info'):
        """Log an event with the specified level and context tag."""
        log_level_int = getattr(logging, level.upper(), logging.INFO)
        self._log_with_context(log_level_int, message, context_tag)
    
    def log_error(self, context_tag: str, message: str):
        self.log_event(context_tag, message, 'error')
    
    def log_warning(self, context_tag: str, message: str):
        self.log_event(context_tag, message, 'warning')
    
    def log_info(self, context_tag: str, message: str, context_override: str = None):
        """
        Logs an info message.
        context_tag: Typically the source of the log (e.g., device name, SIM_EVENT).
        message: The log message.
        context_override: If provided, this will be used as the [sim_context] in the log instead of context_tag.
                         Useful for global messages like "SIM_INIT" where context_tag might be too generic.
        """
        effective_context = context_override if context_override is not None else context_tag
        self._log_with_context(logging.INFO, message, effective_context)

    def store_simulation_metrics(self, simulation_run_key: str, metrics_dict: Dict):
        """
        Store metrics for a specific simulation run (e.g., 'lab_framework_on').
        """
        self.simulation_metrics[simulation_run_key] = metrics_dict
        self.log_info("METRICS_STORE", f"Metrics stored for run key: {simulation_run_key}", context_override=self.simulation_name)

    def log_comparison(self, simulation_type_for_comparison_key: str):
        """
        Log comparison between 'framework_on' and 'framework_off' runs
        for a given simulation type (e.g., 'lab' or 'building').
        """
        key_on = f"{simulation_type_for_comparison_key.lower()}_framework_on"
        key_off = f"{simulation_type_for_comparison_key.lower()}_framework_off"

        self.log_info("COMPARISON_START", f"Attempting comparison for base key: {simulation_type_for_comparison_key}", context_override=self.simulation_name)

        if key_on in self.simulation_metrics and key_off in self.simulation_metrics:
            metrics_on = self.simulation_metrics[key_on]
            metrics_off = self.simulation_metrics[key_off]
            
            comparison_lines = [
                f"\n--- Comparison for {simulation_type_for_comparison_key.upper()} ---",
                f"{'Metric':<35} | {'Framework ON':<20} | {'Framework OFF':<20} | {'Difference (ON - OFF)':<25}",
                "-"*105
            ]
            
            # Define metrics to compare (keys should exist in your metrics dict from the simulation)
            # These keys are based on the `lab_simulation.py` metrics structure
            metrics_to_compare = [
                'jobs_completed_on_time', 'jobs_completed_late', 'jobs_failed_deadline',
                'total_rewards_earned', 'total_penalties_incurred', 
                'avg_job_completion_time', 'avg_job_tardiness',
                'avg_trust_at_end', # Will be N/A for framework_off
                'final_total_balance_network'
            ]

            for metric_key in metrics_to_compare:
                val_on = metrics_on.get(metric_key)
                val_off = metrics_off.get(metric_key)
                
                diff_str = "N/A"
                val_on_str = f"{val_on:.2f}" if isinstance(val_on, float) else str(val_on if val_on is not None else "N/A")
                val_off_str = f"{val_off:.2f}" if isinstance(val_off, float) else str(val_off if val_off is not None else "N/A")

                if isinstance(val_on, (int, float)) and isinstance(val_off, (int, float)):
                    diff = val_on - val_off
                    diff_str = f"{diff:.2f}" if isinstance(diff, float) else str(diff)
                
                comparison_lines.append(f"{metric_key:<35} | {val_on_str:<20} | {val_off_str:<20} | {diff_str:<25}")
            
            comparison_output = "\n".join(comparison_lines)
            self.log_info("COMPARISON_RESULT", comparison_output, context_override=self.simulation_name)
        else:
            missing_keys = []
            if key_on not in self.simulation_metrics: missing_keys.append(key_on)
            if key_off not in self.simulation_metrics: missing_keys.append(key_off)
            self.log_info("COMPARISON_FAIL", f"Could not perform comparison for {simulation_type_for_comparison_key}. Missing data for run key(s): {', '.join(missing_keys)}. Available keys: {list(self.simulation_metrics.keys())}", context_override=self.simulation_name)
        self.log_info("COMPARISON_END", f"Comparison finished for base key: {simulation_type_for_comparison_key}", context_override=self.simulation_name)

