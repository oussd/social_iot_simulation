import random
import time
from enum import Enum
from ..utils.logger import SimulationLogger

# QoS/QoE ENHANCEMENT: Define QoE Levels
class QoELevel(Enum):
    BAD = 0
    FAIR = 1
    GOOD = 2

class Device:
    def __init__(self, device_id, name, max_load=100):
        self.device_id = device_id
        self.name = name
        self.max_load = max_load
        self.current_load = 0
        self.trust_score = 75.0  # Start with a neutral-to-good general trust score
        self.relationships = {
            'work_with_me': [], 'work_for_me': [], 'controller_for': [],
            'back_me': [], 'avoid_me': []
        }
        self.policy = {
            'max_tasks_per_controller': 10, 'max_load_per_controller': 50, 'task_timeout': 300
        }
        self.task_log = [] # Consider limiting size if it grows too large
        self.misuse_count = 0
        self.blame_count = 0
        self.controller_tasks = {} # Tracks tasks assigned by this device if it's a controller
        self.logger = SimulationLogger()

        # --- Monetary Attributes ---
        self.balance = 1000
        self.min_acceptable_income_threshold = 50
        self.current_period_income = 0
        self.total_income_earned = 0
        self.total_expenses_paid = 0
        self.total_penalties_applied_to_others = 0
        self.total_penalties_received = 0
        self.task_failure_penalty_value = 15
        self.policy_violation_penalty_value = 25

        # --- QoS/QoE Attributes ---
        self.announced_qos = { # What this device claims/aims to provide
            'response_time_ms': float(random.uniform(30, 70)), # Device's typical processing + internal latency
            'task_success_rate': random.uniform(0.90, 0.99),
            'load_efficiency': random.uniform(0.9, 1.1), # 1.0 is ideal, >1 uses more load than expected
        }
        # What this device expects from others when it's a requester
        self.expected_partner_qos = {
            'response_time_ms': float(random.uniform(40, 80)),
            'task_success_rate': random.uniform(0.85, 0.95),
        }
        self.qoe_thresholds = { # For |Announced - Measured|
            'response_time_ms': {'sigma': 25.0, 'delta': 15.0}, # Wider range for response time
            'task_success_rate': {'sigma': 0.15, 'delta': 0.10}, # For difference from expected success rate
            'load_efficiency': {'sigma': 0.25, 'delta': 0.15}
        }
        self.interaction_history = [] # Limited list of {'partner_id', 'task_type', 'role', 'measured_qos', 'avg_qoe', 'timestamp'}
        self.max_interaction_history_len = 20
        self.trust_adjustment_factor = 5.0 # Max trust change per interaction based on QoE


    # --- Monetary Methods ---
    def receive_income(self, amount, source_description=""):
        self.balance += amount
        self.total_income_earned += amount
        self.current_period_income += amount
        self.log_event(f"Received income: {amount} from {source_description}. New balance: {self.balance:.2f}")

    def pay_expense(self, amount, recipient_device, description=""):
        if self.balance >= amount:
            self.balance -= amount
            self.total_expenses_paid += amount
            if recipient_device:
                recipient_device.receive_income(amount, f"expense payment from {self.name} for {description}")
            self.log_event(f"Paid expense: {amount:.2f} to {recipient_device.name if recipient_device else description}. New balance: {self.balance:.2f}")
            return True
        else:
            self.log_event(f"Failed to pay expense: {amount:.2f} (insufficient balance: {self.balance:.2f})")
            # This failure to pay could be a BAD QoS event if the payment was an obligation
            # self.update_trust_from_qoe(recipient_device, "payment_obligation", {'task_success_binary': 0}, interaction_role="performer")
            return False

    def apply_penalty_to_device(self, target_device, penalty_amount, reason=""):
        self.log_event(f"Applying penalty: {penalty_amount:.2f} to {target_device.name} for {reason}.")
        target_device.receive_penalty(penalty_amount, self.name, reason)
        self.total_penalties_applied_to_others += penalty_amount

    def receive_penalty(self, penalty_amount, penalized_by="System/IoTApp", reason=""):
        self.balance -= penalty_amount
        self.total_penalties_received += penalty_amount
        self.log_event(f"Received penalty: {penalty_amount:.2f} from {penalized_by} for {reason}. New balance: {self.balance:.2f}")
        # Direct impact on trust for receiving a penalty
        direct_trust_hit = -10.0 # More severe than a single bad QoE usually
        self.trust_score = max(0.0, min(100.0, self.trust_score + direct_trust_hit))
        self.log_event(f"Direct trust hit from penalty: {direct_trust_hit:.1f}. New trust: {self.trust_score:.1f}")

    def check_min_income_satisfied(self):
        satisfied = self.current_period_income >= self.min_acceptable_income_threshold
        if not satisfied:
            self.log_event(f"Warning: Min income ({self.min_acceptable_income_threshold:.2f}) not met for period (earned: {self.current_period_income:.2f}).")
        self.current_period_income = 0 # Reset for next period
        return satisfied

    # --- Relationship Methods ---
    def add_relationship(self, relation_type, device, constraints=None):
        if relation_type in self.relationships:
            if not any(r['device'] == device for r in self.relationships[relation_type]):
                self.relationships[relation_type].append({
                    'device': device, 'constraints': constraints or {},
                    'start_time': time.time(), 'status': 'active'
                })
                self.log_event(f"Added '{relation_type}' relationship with {device.name}")

    def avoid(self, device):
        if 'avoid_me' not in self.relationships or not isinstance(self.relationships['avoid_me'], list):
            self.relationships['avoid_me'] = []
        if not any(r['device'] == device for r in self.relationships['avoid_me']):
            self.relationships['avoid_me'].append({'device': device, 'status': 'active', 'start_time': time.time()})
            self.log_event(f"Avoiding device {device.name}")

    # --- Load and Policy Methods ---
    def negotiate_load(self, requested_load): # Check if CAN take load
        return self.current_load + requested_load <= self.max_load

    def consume_load(self, load_amount): # Actually add load
        if self.current_load + load_amount <= self.max_load:
            self.current_load += load_amount
            return True
        # If it would exceed, don't add, but log it as an issue if action was attempted
        self.log_event(f"Attempted to consume load {load_amount} but would exceed max_load {self.max_load}. Current: {self.current_load}")
        return False

    def reduce_load(self, amount=None):
        if amount is None: amount = random.randint(max(1,int(self.current_load*0.1)), max(2,int(self.current_load*0.3))) # Reduce a percentage
        self.current_load = max(0, self.current_load - amount)

    def check_policy(self, relation_type_context, task_type, from_device_partner, details=None):
        # Example: Check if task is forbidden by a 'work_with_me' partner's constraints
        # This needs to be specific to the active relationship with from_device_partner
        for rel_list in self.relationships.values():
            for rel in rel_list:
                if rel['device'] == from_device_partner: # Found the specific relationship
                    constraints = rel.get('constraints', {})
                    if 'forbidden_tasks' in constraints and task_type in constraints['forbidden_tasks']:
                        self.log_event(f"Policy violation with {from_device_partner.name}: Task '{task_type}' forbidden.")
                        # This device violated policy towards partner, partner might penalize.
                        # For self, this is a blame.
                        self.blame_count +=1
                        self.receive_penalty(self.policy_violation_penalty_value, "Policy Self-Violation", f"Task {task_type} to {from_device_partner.name}")
                        return False # Policy violation
        return True # No violation found or no specific constraint against it

    def add_controller(self, controller_device, constraints=None):
        if not any(d['device'] == controller_device for d in self.relationships['work_for_me']):
            self.relationships['work_for_me'].append({
                'device': controller_device, 'constraints': constraints or {}, 'start_time': time.time(),
                'status': 'active', 'task_count': 0, 'total_load_assigned': 0})
            self.log_event(f"Added {controller_device.name} as controller (I work for them)")
            return True
        return False

    def remove_controller(self, controller_device):
        self.relationships['work_for_me'] = [r for r in self.relationships['work_for_me'] if r['device'] != controller_device]
        self.log_event(f"Removed {controller_device.name} as controller")

    def is_authorized_controller(self, device):
        return any(r['device'] == device and r['status'] == 'active' for r in self.relationships.get('work_for_me', []))

    def check_controller_limits(self, controller_device, load_of_this_task):
        for rel in self.relationships.get('work_for_me', []):
            if rel['device'] == controller_device:
                # Check ODRL-like constraints (count, load, time if defined in rel['constraints'])
                if rel.get('task_count',0) >= rel.get('constraints',{}).get('max_tasks', self.policy['max_tasks_per_controller']):
                    self.log_event(f"Controller {controller_device.name} exceeded max tasks policy.")
                    self.misuse_count +=1
                    return False
                if rel.get('total_load_assigned',0) + load_of_this_task > rel.get('constraints',{}).get('max_load', self.policy['max_load_per_controller']):
                    self.log_event(f"Controller {controller_device.name} exceeded max load policy.")
                    self.misuse_count +=1
                    return False
                return True
        return False # Not a recognized controller or no active relation

    def update_controller_metrics(self, controller_device, load_of_this_task):
        for rel in self.relationships.get('work_for_me', []):
            if rel['device'] == controller_device:
                rel['task_count'] = rel.get('task_count', 0) + 1
                rel['total_load_assigned'] = rel.get('total_load_assigned', 0) + load_of_this_task; break

    # --- QoS/QoE and Trust Update Methods ---
    def _calculate_qoe_level_for_param(self, qos_param_name, announced_val, measured_val):
        """Calculates QoE for a single QoS parameter based on |Announced - Measured|."""
        if announced_val is None or measured_val is None: return QoELevel.FAIR # Cannot assess
        if qos_param_name not in self.qoe_thresholds:
            self.log_event(f"Warning: QoE thresholds undefined for '{qos_param_name}'. Assuming FAIR.")
            return QoELevel.FAIR

        # For rates (0-1), a direct difference is fine.
        # For response time, it's also a direct difference.
        # For success (binary 0 or 1), announced is typically 1 (or high rate like 0.95).
        # If announced is a rate (e.g. 0.95) and measured is binary (0 or 1),
        # then diff for success is |0.95 - 1| = 0.05 (good), for failure is |0.95 - 0| = 0.95 (bad).
        
        sigma = self.qoe_thresholds[qos_param_name]['sigma']
        delta = self.qoe_thresholds[qos_param_name]['delta']
        diff = abs(announced_val - measured_val)

        # Invert logic for parameters where lower measured is better (e.g. response time, bad load_efficiency > 1)
        # This is simplified; a proper model would define if higher/lower is better per QoS param.
        # For now, we assume announced_val is the ideal target.
        if qos_param_name == 'response_time_ms': # Lower measured is better, but formula is |A-M|
             pass # The |A-M| formula inherently handles this if A is the target.
        elif qos_param_name == 'load_efficiency': # M > A is bad if A is 1.0 (ideal)
             pass # |A-M| handles it.

        if diff < (sigma - delta): return QoELevel.GOOD
        elif diff < (sigma + delta): return QoELevel.FAIR
        else: return QoELevel.BAD

    def update_trust_from_qoe(self, partner_device, task_type, measured_qos_params, interaction_role):
        """
        Updates this device's trust score (general or in partner_device) based on QoE.
        interaction_role: 'performer' (this device did the task for partner),
                          'requester' (this device asked partner to do the task).
        measured_qos_params: Dict from the performer, e.g., {'task_success_binary': 1, 'response_time_ms': 55.0, 'load_consumed': 10}
        """
        # This method updates THIS device's trust.
        # If role is 'performer', it updates its own general trust based on its performance.
        # If role is 'requester', it updates its trust IN THE PARTNER based on partner's performance.
        # For now, we only update the general self.trust_score. Per-partner trust is a TODO.

        qoe_values_for_agg = []
        log_qoe_details = []

        # Determine the set of announced/expected QoS parameters to use
        if interaction_role == "performer": # This device performed, compare to its own announced_qos
            announced_qos_set = self.announced_qos
        elif interaction_role == "requester": # This device requested, compare to its expected_partner_qos
            announced_qos_set = self.expected_partner_qos
        else: # E.g. self-assessment not tied to a partner
            announced_qos_set = self.announced_qos


        # 1. Task Success (Binary)
        if 'task_success_binary' in measured_qos_params:
            announced_sr = announced_qos_set.get('task_success_rate', 1.0) # Default to expecting 100% success
            qoe_sr = self._calculate_qoe_level_for_param('task_success_rate', announced_sr, measured_qos_params['task_success_binary'])
            qoe_values_for_agg.append(qoe_sr.value)
            log_qoe_details.append(f"SR QoE:{qoe_sr.name}(E:{announced_sr*100:.0f}%,A:{measured_qos_params['task_success_binary']*100:.0f}%)")

        # 2. Response Time (if available)
        if 'response_time_ms' in measured_qos_params:
            announced_rt = announced_qos_set.get('response_time_ms')
            if announced_rt is not None:
                qoe_rt = self._calculate_qoe_level_for_param('response_time_ms', announced_rt, measured_qos_params['response_time_ms'])
                qoe_values_for_agg.append(qoe_rt.value)
                log_qoe_details.append(f"RT QoE:{qoe_rt.name}(E:{announced_rt:.0f},A:{measured_qos_params['response_time_ms']:.0f}ms)")

        # 3. Load Efficiency (relevant if this device was the performer)
        if interaction_role == "performer" and 'load_consumed' in measured_qos_params and 'expected_load_for_task' in measured_qos_params:
            announced_le = announced_qos_set.get('load_efficiency', 1.0) # Ideal efficiency
            expected_task_load = measured_qos_params['expected_load_for_task']
            actual_task_load = measured_qos_params['load_consumed']
            
            measured_efficiency = actual_task_load / expected_task_load if expected_task_load > 0 else 1.0
            
            qoe_le = self._calculate_qoe_level_for_param('load_efficiency', announced_le, measured_efficiency)
            qoe_values_for_agg.append(qoe_le.value)
            log_qoe_details.append(f"LE QoE:{qoe_le.name}(E_eff:{announced_le:.2f},A_eff:{measured_efficiency:.2f} from E_load:{expected_task_load},A_load:{actual_task_load})")


        if not qoe_values_for_agg:
            # self.log_event(f"No QoS params to calculate QoE for interaction with {partner_device.name if partner_device else 'N/A'} for {task_type}.")
            return

        avg_qoe_numeric = sum(qoe_values_for_agg) / len(qoe_values_for_agg) # Average of (0, 1, 2)

        # Translate average QoE (0-2) to a trust score adjustment
        delta_trust = (avg_qoe_numeric - QoELevel.FAIR.value) * self.trust_adjustment_factor

        # If this device is a requester, it's updating trust IN THE PARTNER.
        # For now, all updates go to self.trust_score (general trust). This needs refinement for per-partner trust.
        # If we had self.trust_in_partners = {}, we'd update self.trust_in_partners[partner_device.device_id]
        target_entity_name = partner_device.name if interaction_role == "requester" and partner_device else self.name +" (self)"

        self.trust_score = max(0.0, min(100.0, self.trust_score + delta_trust)) # Update general trust for now
        
        self.log_event(f"QoE-Trust ({interaction_role} for task '{task_type}' with {partner_device.name if partner_device else 'Self/System'}): "
                       f"{', '.join(log_qoe_details)}. AvgQoE:{avg_qoe_numeric:.2f}. dT:{delta_trust:.1f}. "
                       f"New Gen.Trust for {self.name}:{self.trust_score:.1f}")

        # Store interaction for history (could be used for per-partner trust later)
        interaction_record = {
            'partner_id': partner_device.device_id if partner_device else None,
            'task_type': task_type, 'role': interaction_role, 'measured_qos': measured_qos_params,
            'avg_qoe': avg_qoe_numeric, 'timestamp': time.time() }
        self.interaction_history.append(interaction_record)
        if len(self.interaction_history) > self.max_interaction_history_len: self.interaction_history.pop(0)


    def handle_request(self, from_device, task_type, load_requested=10, details=None):
        """
        Base handler for requests. Subclasses will call this then add their specific logic.
        Returns a dict: {'success': bool, 'reason': str, 'measured_qos_for_requestor': dict, 'request_start_time': float}
        'measured_qos_for_requestor' contains QoS aspects of THIS device's attempt to handle, from requestor's POV.
        """
        details = details or {}
        request_start_time = time.time()
        measured_qos_outcome = {'response_time_ms': 0.0, 'task_success_binary': 0} # Initialize

        if any(r['device'] == from_device for r in self.relationships.get('avoid_me', [])):
            self.log_event(f"Rejected (AVOIDED) request for '{task_type}' from {from_device.name if from_device else 'N/A'}")
            measured_qos_outcome['response_time_ms'] = (time.time() - request_start_time) * 1000
            # This device (self) successfully enforced its 'avoid' policy. Not necessarily a trust hit for self.
            # from_device would have a bad QoE with this device.
            return {'success': False, 'reason': 'avoided_device', 'measured_qos_for_requestor': measured_qos_outcome, 'request_start_time': request_start_time}

        is_controller_req = self.is_authorized_controller(from_device)
        if is_controller_req and not self.check_controller_limits(from_device, load_requested):
            self.log_event(f"Rejected (CONTROLLER_LIMITS) request for '{task_type}' from {from_device.name}")
            measured_qos_outcome['response_time_ms'] = (time.time() - request_start_time) * 1000
            # This device correctly rejected a misbehaving controller. This is GOOD for self.
            # self.update_trust_from_qoe(from_device, "controller_policy_enforcement", {'task_success_binary': 1}, interaction_role="performer")
            # from_device (controller) had a bad interaction with self (its request was denied for good reason)
            return {'success': False, 'reason': 'controller_limits_exceeded', 'measured_qos_for_requestor': measured_qos_outcome, 'request_start_time': request_start_time}

        # Check general policies for this interaction (e.g. if from_device is a work-with-me partner)
        if from_device and not self.check_policy('work_with_me', task_type, from_device, details):
            # Self violated a policy it had with from_device
            measured_qos_outcome['response_time_ms'] = (time.time() - request_start_time) * 1000
            # Update self trust based on this self-acknowledged policy violation (bad performance)
            self.update_trust_from_qoe(from_device, task_type, {'task_success_binary': 0, 'policy_adherence_binary':0}, interaction_role="performer")
            return {'success': False, 'reason': 'policy_violation_generic', 'measured_qos_for_requestor': measured_qos_outcome, 'request_start_time': request_start_time}


        if not self.negotiate_load(load_requested): # Check if device CAN take load
            self.misuse_count += 1 # Counts as a form of unavailability
            self.log_event(f"Rejected (OVERLOAD) request for '{task_type}' from {from_device.name if from_device else 'N/A'}")
            measured_qos_outcome['response_time_ms'] = (time.time() - request_start_time) * 1000
            # This device was unavailable. Bad QoS for from_device.
            # Self-assessment: performer (self) failed due to overload.
            self.update_trust_from_qoe(from_device, task_type, {'task_success_binary': 0, 'availability_binary':0}, interaction_role="performer")
            return {'success': False, 'reason': 'overload', 'measured_qos_for_requestor': measured_qos_outcome, 'request_start_time': request_start_time}

        # If all checks pass, provisionally accept. Subclass will do the work.
        self.log_event(f"Provisionally accepted task '{task_type}' from {from_device.name if from_device else 'N/A'} (load_requested: {load_requested})")
        if is_controller_req: self.update_controller_metrics(from_device, load_requested)
        
        # Subclass needs to consume load using self.consume_load(actual_load_for_task)
        return {'success': True, 'reason': 'accepted_by_base_policy_and_load', 'request_start_time': request_start_time}


    def log_event(self, message):
        self.logger.log_info(f"{self.name}({self.device_id})", message)

    def report_status(self):
        trust_str = f"Trust:{self.trust_score:.1f}"
        load_str = f"Load:{self.current_load}/{self.max_load}"
        bal_str = f"Bal:{self.balance:.0f}"
        inc_str = f"Inc:{self.total_income_earned:.0f}"
        exp_str = f"Exp:{self.total_expenses_paid:.0f}"
        pen_str = f"PenRcv:{self.total_penalties_received:.0f}"
        misu_str = f"Misu:{self.misuse_count}"
        blame_str = f"Blame:{self.blame_count}"
        rels = [f"{k.split('_')[0][:2]}:{len(v)}" for k,v in self.relationships.items() if v]
        rel_str = f"Rel:[{','.join(rels)}]" if rels else "Rel:[0]"
        
        self.logger.log_info(f"{self.nameShort()}", f"{trust_str} {bal_str} {load_str} {inc_str} {exp_str} {pen_str} {misu_str} {blame_str} {rel_str}")

    def nameShort(self): # Helper for shorter logs
        return f"{self.name.replace('Device','').replace('Lab','L').replace('Sensor','S').replace('Actuator','A').replace('Comm','C').replace('Composite','Co')}({self.device_id.replace('lab_','').replace('sens','s').replace('act','a').replace('comm','c').replace('comp','co')})"