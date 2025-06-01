import logging
import time
import os
from typing import Dict, Any, List, Optional

class SimulationLogger:
    _instance = None
    _initialized_loggers: Dict[str, logging.Logger] = {}

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SimulationLogger, cls).__new__(cls)
            cls._instance._initialized_with_sim_name = False
        return cls._instance

    def __init__(self, simulation_name: str = "Default_SimSet", log_to_console: bool = True, log_to_file: bool = True):
        if hasattr(self, '_initialized_with_sim_name') and self._initialized_with_sim_name and \
           hasattr(self, 'overall_simulation_name') and self.overall_simulation_name == simulation_name:
            return

        self.overall_simulation_name = simulation_name
        self.log_file_base = "sim_run_details"
        logger_object_name = f"SIoT_Logger_{self.overall_simulation_name}_{id(self)}"

        if logger_object_name in self._initialized_loggers:
            self.logger = self._initialized_loggers[logger_object_name]
        else:
            self.logger = logging.getLogger(logger_object_name)
            self.logger.handlers = []
            self.logger.setLevel(logging.INFO) # Set to INFO by default
            # For debugging specific modules, you might want to set their loggers to DEBUG
            # e.g., logging.getLogger('src.devices.device').setLevel(logging.DEBUG)
            self.logger.propagate = False
            if not os.path.exists('logs'):
                os.makedirs('logs')
            formatter = logging.Formatter('%(asctime)s [%(levelname)-5s] [%(sim_context)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            if log_to_file:
                current_timestamp = time.strftime('%Y%m%d_%H%M%S')
                log_filename = f"logs/{self.log_file_base}_{self.overall_simulation_name.replace(' ','_')}_{current_timestamp}.log"
                file_handler = logging.FileHandler(log_filename, mode='w')
                file_handler.setLevel(logging.DEBUG) # Log DEBUG and above to file
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            if log_to_console:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.INFO) # Log INFO and above to console
                console_handler.setFormatter(formatter)
                self.logger.addHandler(console_handler)
            if not self.logger.handlers:
                self.logger.addHandler(logging.NullHandler())
            self._initialized_loggers[logger_object_name] = self.logger

        self.simulation_metrics_storage: Dict[str, Dict[str, Any]] = {}
        self._initialized_with_sim_name = True
        if hasattr(self, 'logger'):
             self.log_info("LOGGER_SETUP", f"Logger initialized for overall simulation set: {self.overall_simulation_name}", context_override=self.overall_simulation_name)
        else:
            print(f"CRITICAL_LOGGER_ERROR: Logger object not available during init for {self.overall_simulation_name}")

    def _log_with_context(self, level: int, message: str, context: str):
        if not hasattr(self, 'logger'):
            print(f"ERROR: Logger not initialized. Message: [{context}] {message}")
            return
        extra_dict = {'sim_context': context}
        self.logger.log(level, message, extra=extra_dict)

    def log_event(self, context_tag: str, message: str, level: str = 'info', context_override: Optional[str] = None):
        log_level_int = getattr(logging, level.upper(), logging.INFO)
        effective_context = context_override if context_override is not None else context_tag
        self._log_with_context(log_level_int, message, effective_context)

    def log_error(self, context_tag: str, message: str, context_override: Optional[str] = None):
        self.log_event(context_tag, message, 'error', context_override=context_override)

    def log_warning(self, context_tag: str, message: str, context_override: Optional[str] = None):
        self.log_event(context_tag, message, 'warning', context_override=context_override)

    def log_info(self, context_tag: str, message: str, context_override: Optional[str] = None):
        self.log_event(context_tag, message, 'info', context_override=context_override)
    
    def log_debug(self, context_tag: str, message: str, context_override: Optional[str] = None): # Added for completeness
        self.log_event(context_tag, message, 'debug', context_override=context_override)


    def store_simulation_metrics(self, simulation_run_key: str, metrics_dict: Dict[str, Any]):
        self.simulation_metrics_storage[simulation_run_key] = metrics_dict
        self.log_info("METRICS_STORED", f"Metrics stored for run key: {simulation_run_key}", context_override=self.overall_simulation_name)

    def log_comparison(self, simulation_type_for_comparison_key: str, variant_keys_in_order: List[str]):
        self.log_info("COMPARISON_START", f"Attempting comparison for base key: {simulation_type_for_comparison_key}", context_override=self.overall_simulation_name)
        
        # Construct the full run keys in the correct format
        full_run_keys = [f"{simulation_type_for_comparison_key}_{vk}" for vk in variant_keys_in_order]
        available_metrics_data: Dict[str, Dict[str, Any]] = {}
        all_keys_present = True
        
        for key_to_check in full_run_keys:
            if key_to_check in self.simulation_metrics_storage:
                available_metrics_data[key_to_check] = self.simulation_metrics_storage[key_to_check]
            else:
                self.log_warning("COMPARISON_DATA_MISSING", f"Metrics data missing for run key: {key_to_check}", context_override=self.overall_simulation_name)
                all_keys_present = False
        
        if not all_keys_present or not available_metrics_data:
            self.log_error("COMPARISON_FAIL", f"Cannot perform comparison for {simulation_type_for_comparison_key}. Insufficient data. Available stored keys: {list(self.simulation_metrics_storage.keys())}", context_override=self.overall_simulation_name)
            return

        # Format the comparison table header
        header_parts = [f"{'Metric':<38}"]
        for run_key_header in full_run_keys:
            variant_name_for_header = run_key_header.split('_')[-1].replace("_", " ").title()
            header_parts.append(f"{variant_name_for_header:<25}")

        comparison_lines = [
            "\n" + "="*30 + f" {simulation_type_for_comparison_key.upper()} FRAMEWORK COMPARISON " + "="*30,
            "|".join(header_parts),
            "-" * (38 + len(full_run_keys) * 26)
        ]

        # Define the metrics to display in order
        metrics_to_display = [
            'total_jobs_created',
            'total_jobs_done',
            'jobs_completed_on_time',
            'jobs_completed_late',
            'jobs_failed_deadline',
            'jobs_failed_internal',
            'total_rewards_earned',
            'total_penalties_incurred',
            'avg_job_completion_time',
            'avg_job_tardiness',
            'avg_trust_at_end',
            'final_total_balance_network',
            'delegation_to_zone_controller_count',
            'delegation_to_primitive_count',
            'successful_negotiations',
            'failed_negotiations',
            'back_me_invocations_successful',
            'back_me_invocations_failed',
            'misuse_incidents_detected',
            'selfish_rejections',
            'faulty_device_actions_failed',
            'unresponsive_device_rejections',
            'total_policy_violations_blamed'
        ]

        # Generate the comparison table rows
        for metric_key_display in metrics_to_display:
            line_parts = [f"{metric_key_display:<38}"]
            for run_key_data in full_run_keys:
                val = available_metrics_data.get(run_key_data, {}).get(metric_key_display)
                val_str = "N/A"
                if val is not None:
                    if isinstance(val, float):
                        val_str = f"{val:.2f}"
                    elif isinstance(val, int):
                        val_str = str(val)
                    elif isinstance(val, str):
                        val_str = val
                line_parts.append(f"{val_str:<25}")
            comparison_lines.append("|".join(line_parts))

        comparison_output = "\n".join(comparison_lines)
        self.log_info("COMPARISON_RESULT", comparison_output, context_override=self.overall_simulation_name)
        self.log_info("COMPARISON_END", f"Comparison finished for base key: {simulation_type_for_comparison_key}", context_override=self.overall_simulation_name)
