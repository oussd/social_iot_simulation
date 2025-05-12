import logging
import time 
import os
from typing import Dict, Any, List # Added List

class SimulationLogger:
    _instance = None
    _initialized_loggers: Dict[str, logging.Logger] = {} # Store loggers by name to avoid re-adding handlers

    def __new__(cls, *args, **kwargs):
        # Singleton behavior is tricky if __init__ takes args that should differentiate instances.
        # For this use case, main.py creates ONE logger and passes it around.
        # If multiple distinct loggers were needed, the singleton would need refinement or removal.
        if cls._instance is None:
            cls._instance = super(SimulationLogger, cls).__new__(cls)
            cls._instance._initialized_with_sim_name = False # Flag to ensure __init__ logic runs correctly once
        return cls._instance

    def __init__(self, simulation_name: str = "Default_SimSet", log_to_console: bool = True, log_to_file: bool = True):
        # This init can be called multiple times by different parts if not careful with singleton access.
        # The _initialized_with_sim_name flag ensures core setup happens once for a given overall simulation set.
        if hasattr(self, '_initialized_with_sim_name') and self._initialized_with_sim_name and self.overall_simulation_name == simulation_name:
            return 

        self.overall_simulation_name = simulation_name # e.g., "lab_ComparisonRun" or "building_ComparisonRun"
        self.log_file_base = "sim_run_details" 
        
        # Core logger setup for this specific simulation_name instance
        # Use a unique name for the logger object itself to avoid conflicts if multiple SimulationLogger instances were made
        logger_object_name = f"SIoT_Logger_{self.overall_simulation_name}_{id(self)}"
        
        if logger_object_name in self._initialized_loggers:
            self.logger = self._initialized_loggers[logger_object_name]
        else:
            self.logger = logging.getLogger(logger_object_name)
            self.logger.handlers = [] 
            self.logger.setLevel(logging.INFO)
            self.logger.propagate = False 

            if not os.path.exists('logs'):
                os.makedirs('logs')
            
            formatter = logging.Formatter('%(asctime)s [%(levelname)-5s] [%(sim_context)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

            if log_to_file:
                current_timestamp = time.strftime('%Y%m%d_%H%M%S')
                log_filename = f"logs/{self.log_file_base}_{self.overall_simulation_name.replace(' ','_')}_{current_timestamp}.log"
                file_handler = logging.FileHandler(log_filename, mode='w') 
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

            if log_to_console:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.INFO)
                console_handler.setFormatter(formatter)
                self.logger.addHandler(console_handler)
            
            if not self.logger.handlers: 
                self.logger.addHandler(logging.NullHandler())
            
            self._initialized_loggers[logger_object_name] = self.logger
        
        self.simulation_metrics_storage: Dict[str, Dict[str, Any]] = {} 
        self._initialized_with_sim_name = True
        self.log_info("LOGGER_INIT", f"Logger initialized for overall simulation set: {self.overall_simulation_name}", context_override=self.overall_simulation_name)

    def _log_with_context(self, level: int, message: str, context: str):
        extra_dict = {'sim_context': context}
        self.logger.log(level, message, extra=extra_dict)

    def log_event(self, context_tag: str, message: str, level: str = 'info'):
        log_level_int = getattr(logging, level.upper(), logging.INFO)
        self._log_with_context(log_level_int, message, context_tag)
    
    def log_error(self, context_tag: str, message: str):
        self.log_event(context_tag, message, 'error')
    
    def log_warning(self, context_tag: str, message: str):
        self.log_event(context_tag, message, 'warning')
    
    def log_info(self, context_tag: str, message: str, context_override: Optional[str] = None):
        effective_context = context_override if context_override is not None else context_tag
        self._log_with_context(logging.INFO, message, effective_context)

    def store_simulation_metrics(self, simulation_run_key: str, metrics_dict: Dict[str, Any]):
        """ Stores metrics for a specific simulation run (e.g., 'building_baseline'). """
        self.simulation_metrics_storage[simulation_run_key] = metrics_dict
        self.log_info("METRICS_STORED", f"Metrics stored for run key: {simulation_run_key}", context_override=self.overall_simulation_name)

    def log_comparison(self, simulation_type_for_comparison_key: str, variant_keys_in_order: List[str]):
        """
        Log comparison between different framework variants for a simulation type.
        Example variant_keys_in_order: ["baseline", "social_basic", "full_siot"]
        """
        self.log_info("COMPARISON_START", f"Attempting comparison for base key: {simulation_type_for_comparison_key}", context_override=self.overall_simulation_name)

        # Construct the full keys used for storing metrics
        full_run_keys = [f"{simulation_type_for_comparison_key.lower()}_{vk}" for vk in variant_keys_in_order]
        
        available_metrics_data: Dict[str, Dict[str, Any]] = {}
        all_keys_present = True
        for key in full_run_keys:
            if key in self.simulation_metrics_storage:
                available_metrics_data[key] = self.simulation_metrics_storage[key]
            else:
                self.log_warning("COMPARISON_DATA_MISSING", f"Metrics data missing for run key: {key}", context_override=self.overall_simulation_name)
                all_keys_present = False
        
        if not all_keys_present or not available_metrics_data:
            self.log_error("COMPARISON_FAIL", f"Cannot perform comparison for {simulation_type_for_comparison_key}. Insufficient data. Available stored keys: {list(self.simulation_metrics_storage.keys())}", context_override=self.overall_simulation_name)
            return

        # --- Build Comparison Table ---
        header_parts = [f"{'Metric':<35}"]
        for key in full_run_keys:
            # Extract variant name from key for header, e.g., "baseline" from "building_baseline"
            variant_name_for_header = key.replace(f"{simulation_type_for_comparison_key.lower()}_", "").replace("_", " ").title()
            header_parts.append(f"{variant_name_for_header:<25}")
        
        comparison_lines = ["\n" + "="*30 + f" {simulation_type_for_comparison_key.upper()} FRAMEWORK COMPARISON " + "="*30, "|".join(header_parts), "-" * (35 + len(full_run_keys) * 26)]
            
        # Define metrics to compare (ensure these keys exist in your simulation's metrics dict)
        metrics_to_display = [
            'jobs_completed_on_time', 'jobs_completed_late', 'jobs_failed_deadline', 'jobs_failed_internal',
            'total_rewards_earned', 'total_penalties_incurred', 
            'avg_job_completion_time', 'avg_job_tardiness',
            'avg_trust_at_end', 
            'final_total_balance_network',
            'delegation_to_zone_controller_count', 'delegation_to_primitive_count',
            'successful_negotiations', 'failed_negotiations', 'misuse_incidents_detected',
            'back_me_invocations_successful'
        ]

        for metric_key in metrics_to_display:
            line_parts = [f"{metric_key:<35}"]
            for run_key in full_run_keys:
                val = available_metrics_data.get(run_key, {}).get(metric_key)
                val_str = "N/A"
                if val is not None:
                    if isinstance(val, float): val_str = f"{val:.2f}"
                    elif isinstance(val, int): val_str = str(val)
                    elif isinstance(val, str): val_str = val # For "N/A" strings etc.
                line_parts.append(f"{val_str:<25}")
            comparison_lines.append("|".join(line_parts))
            
        comparison_output = "\n".join(comparison_lines)
        self.log_info("COMPARISON_RESULT", comparison_output, context_override=self.overall_simulation_name)
        self.log_info("COMPARISON_END", f"Comparison finished for base key: {simulation_type_for_comparison_key}", context_override=self.overall_simulation_name)

