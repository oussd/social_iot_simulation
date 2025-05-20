import random
import time
import uuid # For unique job IDs
from collections import deque # For job queue
from typing import List, Dict, Any, Optional # Ensure Optional is imported

# Assuming these are in ..devices.device (adjust path if needed)
from ..devices.device import Device, QoELevel
from ..devices.sensing_device import SensingDevice
from ..devices.actuating_device import ActuatingDevice
from ..devices.communicating_device import CommunicatingDevice
from ..devices.composite_device import CompositeDevice
# Ensure your logger is correctly imported
from ..utils.logger import SimulationLogger

# Define a simple Job structure
class Job:
    def __init__(self, job_id: str, creation_time: int, work_units: int,
                 deadline_time: int, base_reward: int, penalty_multiplier: float = 1.5):
        self.id = job_id
        self.creation_time = creation_time
        self.work_units_required = work_units
        self.work_units_done = 0
        self.deadline_time = deadline_time # Absolute simulation time
        self.assigned_to_device_id: Optional[str] = None
        self.status = "PENDING" # PENDING, ASSIGNED, IN_PROGRESS, COMPLETED_ON_TIME, COMPLETED_LATE, FAILED_DEADLINE
        self.completion_time = -1
        self.base_reward = base_reward
        self.penalty_for_failure = int(base_reward * penalty_multiplier)

    def __repr__(self):
        return (f"Job(id={self.id}, wu={self.work_units_done}/{self.work_units_required}, "
                f"dl={self.deadline_time}, status={self.status}, assigned_to={self.assigned_to_device_id})")


class LabSimulation:
    def __init__(self, framework_variant: str = "full_siot", # Changed from framework_enabled
                 num_devices: int = 5,
                 duration_minutes: int = 240,
                 logger_instance: Optional[SimulationLogger] = None,
                 run_context_name: str = "LabSimRun"): # Added run_context_name

        self.framework_variant = framework_variant # Store the variant
        self.num_devices = num_devices
        self.devices: List[Device] = []
        self.time_frame = duration_minutes
        self.run_context_name = run_context_name


        if logger_instance:
            self.logger = logger_instance
        else:
            # Fallback if no logger is provided (though main.py should always provide one)
            self.logger = SimulationLogger(simulation_name=self.run_context_name)

        self.current_minute = 0

        # Job Management
        self.job_queue: deque[Job] = deque()
        self.completed_jobs: List[Job] = []
        self.failed_jobs: List[Job] = []
        self.next_job_id_counter = 0
        self.job_generation_interval = 10
        self.sudden_workload_chance = 0.05

        # Metrics
        # Determine framework mode string based on framework_variant
        if self.framework_variant == "baseline":
            framework_mode_str = "Baseline_No_SIoT"
        elif self.framework_variant == "social_basic":
            framework_mode_str = "Social_Basic"
        elif self.framework_variant == "full_siot":
            framework_mode_str = "Full_SIoT"
        else:
            framework_mode_str = f"Unknown_Framework ({self.framework_variant})"

        self.metrics: Dict[str, Any] = {
            'framework_variant': self.framework_variant, # Store the variant key
            'framework_mode_display': framework_mode_str, # For easier report reading
            'jobs_generated': 0,
            'jobs_assigned':0,
            'jobs_completed_on_time': 0,
            'jobs_completed_late': 0,
            'jobs_failed_deadline': 0,
            'jobs_failed_internal': 0, # Added for consistency with building sim, though not explicitly used yet
            'total_work_units_processed': 0,
            'avg_job_completion_time': 0,
            'avg_job_tardiness': 0,
            'device_cycles_working': {}, # Initialized in setup_devices
            'device_cycles_idle': {},   # Initialized in setup_devices
            'total_rewards_earned': 0,
            'total_penalties_incurred': 0,
            'qoe_interaction_samples': [],
            'avg_trust_at_end': "N/A", # Will be updated correctly based on framework_variant
            'final_total_balance_network': 0,
            'total_income_generated_network': 0,
            'min_income_check_interval': duration_minutes // 8 if duration_minutes >= 80 else 10,
            'misuse_incidents_detected': 0, # Added for consistency
            'back_me_invocations_successful': 0, # Added for consistency
            'back_me_invocations_failed': 0, # Added for consistency
        }
        self.logger.log_info("SIM_INIT", f"Lab Simulation ({self.metrics['framework_mode_display']}) | Devices: {num_devices} | Duration: {self.time_frame}m",
                             context_override=self.run_context_name)

    def _get_next_job_id(self) -> str:
        self.next_job_id_counter += 1
        return f"lab_job_{self.next_job_id_counter}"

    def _generate_jobs(self):
        # Periodic job generation
        if self.current_minute % self.job_generation_interval == 0:
            num_new_jobs = random.randint(1, max(1, self.num_devices // 3))
            for _ in range(num_new_jobs):
                work = random.randint(5, 20)
                deadline = self.current_minute + random.randint(work + 5, work + 30)
                reward = work * random.randint(2,5)
                job = Job(self._get_next_job_id(), self.current_minute, work, deadline, reward)
                self.job_queue.append(job)
                self.metrics['jobs_generated'] += 1
                self.logger.log_info("JOB_GEN", f"New job: {job}", context_override=self.run_context_name)

        # Sudden workload
        if random.random() < self.sudden_workload_chance:
            num_sudden_jobs = random.randint(max(1,self.num_devices // 2), self.num_devices)
            self.logger.log_info("JOB_GEN_EVENT", f"SUDDEN WORKLOAD: Generating {num_sudden_jobs} urgent jobs.", context_override=self.run_context_name)
            for _ in range(num_sudden_jobs):
                work = random.randint(10, 30)
                deadline = self.current_minute + random.randint(work + 2, work + 15) # Tighter deadline
                reward = work * random.randint(3,6) # Potentially higher reward
                job = Job(self._get_next_job_id(), self.current_minute, work, deadline, reward)
                self.job_queue.append(job)
                self.metrics['jobs_generated'] += 1
                self.logger.log_info("JOB_GEN", f"Urgent job: {job}", context_override=self.run_context_name)

    def setup_devices(self):
        device_types_counts = {'sensing': 0, 'actuating': 0, 'communicating': 0, 'composite': 0}
        base_starting_balance = 800
        min_income_per_period = self.metrics.get('min_income_check_interval', 30) * 0.75 # Adjusted

        # Initialize device-specific metrics keys
        for i in range(self.num_devices):
            dev_id_str = f"lab_dev_{i+1}" # More specific ID prefix
            self.metrics['device_cycles_working'][dev_id_str] = 0
            self.metrics['device_cycles_idle'][dev_id_str] = 0

        for i in range(self.num_devices):
            dev_id_str = f"lab_dev_{i+1}"
            dev_type_index = i % 4 # Cycle through device types
            device_instance: Optional[Device] = None

            # Pass framework_variant to each device constructor
            if dev_type_index == 0:
                device_instance = SensingDevice(dev_id_str, f"LabSensor{i+1}", framework_variant=self.framework_variant, logger_instance=self.logger, current_minute_provider=lambda: self.current_minute)
                device_types_counts['sensing'] += 1
            elif dev_type_index == 1:
                device_instance = ActuatingDevice(dev_id_str, f"LabActuator{i+1}", framework_variant=self.framework_variant, logger_instance=self.logger, current_minute_provider=lambda: self.current_minute)
                device_types_counts['actuating'] += 1
            elif dev_type_index == 2:
                device_instance = CommunicatingDevice(dev_id_str, f"LabComm{i+1}", framework_variant=self.framework_variant, logger_instance=self.logger, current_minute_provider=lambda: self.current_minute)
                device_types_counts['communicating'] += 1
            else: # dev_type_index == 3
                device_instance = CompositeDevice(dev_id_str, f"LabComposite{i+1}", framework_variant=self.framework_variant, logger_instance=self.logger, current_minute_provider=lambda: self.current_minute)
                device_types_counts['composite'] += 1

            if device_instance:
                device_instance.balance = base_starting_balance + random.randint(-50, 50)
                device_instance.min_acceptable_income_threshold = min_income_per_period + random.randint(-2, 2)
                device_instance.sim_metrics_ref = self.metrics # Give device a reference to update global sim metrics like misuse
                self.devices.append(device_instance)

        self.logger.log_info("DEV_DIST", f"Total: {self.num_devices} | " + " | ".join([f"{k.capitalize()[:4]}:{v}" for k,v in device_types_counts.items()]), context_override=self.run_context_name)

        # Setup relationships if not in baseline mode
        if self.framework_variant != "baseline":
            rel_counts = {'work_with_me': 0, 'back_me': 0, 'avoid_me': 0, 'controller_for':0, 'work_for_me':0}
            all_composites = [d for d in self.devices if isinstance(d, CompositeDevice)]
            non_composites = [d for d in self.devices if not isinstance(d, CompositeDevice)]

            for comp_dev in all_composites:
                # Composites might control some non-composite devices
                num_workers_for_composite = random.randint(0, max(0, len(non_composites)//len(all_composites) if all_composites else 0))
                possible_workers = random.sample(non_composites, min(len(non_composites), num_workers_for_composite * 2)) # Sample a bit more
                workers_assigned_count = 0
                for worker_cand in possible_workers:
                    if workers_assigned_count < num_workers_for_composite:
                         # Ensure worker isn't already controlled by too many, or this composite
                        if not any(rel.get('device') == comp_dev for rel in worker_cand.relationships.get('work_for_me',[])):
                            if comp_dev.add_worker(worker_cand): # add_worker in Device now, also calls worker.add_controller
                                rel_counts['controller_for'] +=1
                                rel_counts['work_for_me'] +=1
                                workers_assigned_count +=1
                    else: break


            for d1 in self.devices:
                for d2 in self.devices:
                    if d1 == d2: continue
                    # General work_with_me and back_me relationships
                    if random.random() < 0.3:
                        d1.add_relationship('work_with_me', d2); rel_counts['work_with_me'] +=1
                    if random.random() < 0.2:
                        d1.add_relationship('back_me', d2); rel_counts['back_me'] +=1
                    if random.random() < 0.05: # Lower chance of pre-emptive avoid
                        d1.avoid(d2); rel_counts['avoid_me'] +=1
            self.logger.log_info("REL_SETUP", f"Framework: {self.framework_variant} | " + " | ".join([f"{k.replace('_',' ').title()[:7]}:{v}" for k,v in rel_counts.items() if v > 0]), context_override=self.run_context_name)
        else:
            self.logger.log_info("REL_SETUP", "Framework: baseline - No social relationships established.", context_override=self.run_context_name)


    def _assign_jobs_to_devices(self):
        # Get devices that are not currently processing a job
        idle_devices = [dev for dev in self.devices if not getattr(dev, 'current_job_id', None)]
        random.shuffle(idle_devices) # Shuffle to give different devices a chance if multiple are suitable

        for job in list(self.job_queue): # Iterate over a copy if modifying queue
            if job.status == "PENDING":
                if not idle_devices: break # No idle devices left to assign

                assigned_device: Optional[Device] = None
                if self.framework_variant != "baseline":
                    # WITH FRAMEWORK: Select based on trust, load, and capabilities (simplified for lab)
                    # For LabSim, we'll use the select_worker_for_task which sorts by trust and load.
                    # We need a "dummy" requestor for select_worker_for_task, or adapt it.
                    # For now, let's assume system assigns, so we sort idle_devices directly.
                    if idle_devices:
                        sorted_idle_devices = sorted(idle_devices, key=lambda d: (getattr(d, 'trust_score', 0), -d.current_load), reverse=True)
                        # Simplification: Lab simulation jobs don't have strong capability requirements, assign to best available.
                        assigned_device = sorted_idle_devices.pop(0)
                        # Remove from general idle_devices list if we used a copy for sorting
                        if assigned_device in idle_devices: idle_devices.remove(assigned_device)

                else: # BASELINE: Simpler random assignment to an idle device
                    if idle_devices:
                        assigned_device = idle_devices.pop(0)

                if assigned_device:
                    job.assigned_to_device_id = assigned_device.device_id
                    job.status = "ASSIGNED"
                    setattr(assigned_device, 'current_job_id', job.id) # Mark device as busy with this job
                    self.metrics['jobs_assigned'] += 1
                    self.logger.log_info("JOB_ASSIGN", f"Job {job.id} assigned to {assigned_device.nameShort()}", context_override=self.run_context_name)
                    if job in self.job_queue: self.job_queue.remove(job) # Move from pending to active (implicitly)

    def _process_device_job(self, device: Device, job: Job):
        """Simulates one cycle of a device working on its assigned job."""
        if device.current_load >= device.max_load * 0.90: # Device is too overloaded
            self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} on Job {job.id} is OVERLOADED (load: {device.current_load}), no progress.", context_override=self.run_context_name)
            self.metrics['device_cycles_idle'][device.device_id] +=1
            return

        # Simulate work being done.
        # For LabSim, assume 1 WU per cycle if device can consume load.
        # Load consumption for doing work on the job.
        work_load_cost = random.randint(5, 15) # Amount of load one WU costs
        if not device.consume_load(work_load_cost):
            self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} on Job {job.id} could not consume load for work, no progress.", context_override=self.run_context_name)
            self.metrics['device_cycles_idle'][device.device_id] +=1
            return

        job.work_units_done += 1
        self.metrics['total_work_units_processed'] += 1
        self.metrics['device_cycles_working'][device.device_id] +=1
        self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} on Job {job.id}: {job.work_units_done}/{job.work_units_required} WU. Load: {device.current_load}", context_override=self.run_context_name)

        # Check for job completion or failure
        if job.work_units_done >= job.work_units_required:
            job.completion_time = self.current_minute
            if self.current_minute <= job.deadline_time:
                job.status = "COMPLETED_ON_TIME"
                self.metrics['jobs_completed_on_time'] += 1
                device.receive_income(job.base_reward, f"Job {job.id} on time")
                self.metrics['total_rewards_earned'] += job.base_reward
                self.logger.log_info("JOB_COMPLETE", f"Job {job.id} COMPLETED ON TIME by {device.nameShort()}. Reward: {job.base_reward}", context_override=self.run_context_name)
            else:
                job.status = "COMPLETED_LATE"
                self.metrics['jobs_completed_late'] += 1
                reduced_reward = int(job.base_reward * 0.5) # Penalty for being late
                device.receive_income(reduced_reward, f"Job {job.id} late")
                self.metrics['total_rewards_earned'] += reduced_reward
                self.logger.log_info("JOB_COMPLETE", f"Job {job.id} COMPLETED LATE by {device.nameShort()}. Reward: {reduced_reward}", context_override=self.run_context_name)

            self.completed_jobs.append(job)
            setattr(device, 'current_job_id', None) # Device is now free

        elif self.current_minute > job.deadline_time: # Job not done and deadline passed
            job.status = "FAILED_DEADLINE"
            job.completion_time = self.current_minute
            self.metrics['jobs_failed_deadline'] += 1
            device.receive_penalty(job.penalty_for_failure, "System", f"Job {job.id} missed deadline")
            self.metrics['total_penalties_incurred'] += job.penalty_for_failure
            self.logger.log_info("JOB_FAIL", f"Job {job.id} FAILED DEADLINE on {device.nameShort()}. Penalty: {job.penalty_for_failure}", context_override=self.run_context_name)
            self.failed_jobs.append(job)
            setattr(device, 'current_job_id', None) # Device is now free


    def simulate_cycle(self, minute: int):
        self.current_minute = minute
        self.logger.log_info("CYCLE_START", f"Minute: {self.current_minute} ({self.metrics['framework_mode_display']})", context_override=self.run_context_name)

        self._generate_jobs()
        self._assign_jobs_to_devices()

        active_jobs_this_cycle_ids = set() # To track jobs processed by devices

        for device in self.devices:
            current_device_job_id = getattr(device, 'current_job_id', None)
            if current_device_job_id:
                # Find the job object. It should not be in self.job_queue if assigned.
                # It could be in self.completed_jobs or self.failed_jobs if processed in a previous iteration by another logic.
                # Or, more simply, we can iterate through all known jobs.
                job_to_process = None
                # Check all lists where an "in-progress" job might be (though ideally only one place)
                # For LabSim, once assigned, it's implicitly active until completed/failed.
                # We'll find it by ID among all jobs that aren't fully terminal.
                all_potentially_active_jobs = [j for j in self.completed_jobs + self.failed_jobs + list(self.job_queue) if j.id == current_device_job_id]
                if all_potentially_active_jobs:
                    # If a job is already completed/failed, device's current_job_id should be None.
                    # This logic path assumes _process_device_job will set current_job_id to None upon terminal state.
                    # We only care about jobs that are truly "IN_PROGRESS" or just "ASSIGNED".
                    # For simplicity, let's assume if device.current_job_id is set, we find that job.
                    # A more robust way would be an explicit list of "active_jobs_on_devices".
                    # For now, find it in the combined list:
                    found_jobs = [j for j in (self.completed_jobs + self.failed_jobs + list(self.job_queue)) if j.id == current_device_job_id and j.status in ["ASSIGNED", "IN_PROGRESS"]]
                    if found_jobs:
                        job_to_process = found_jobs[0]


                if job_to_process:
                    if job_to_process.status == "ASSIGNED":
                        job_to_process.status = "IN_PROGRESS"
                        self.logger.log_info("JOB_START", f"Device {device.nameShort()} starting Job {job_to_process.id}", context_override=self.run_context_name)

                    if job_to_process.status == "IN_PROGRESS": # Ensure it's still in progress
                         self._process_device_job(device, job_to_process)
                         active_jobs_this_cycle_ids.add(job_to_process.id)

                elif current_device_job_id: # Device thinks it has a job, but we couldn't find it as active
                    self.logger.log_warning("STATE_CLEANUP", f"Device {device.nameShort()} had stale job ID {current_device_job_id}. Clearing.", context_override=self.run_context_name)
                    setattr(device, 'current_job_id', None)
            else: # Device is idle
                 self.metrics['device_cycles_idle'][device.device_id] +=1
                 # Simulate background SIoT interactions if framework is on
                 if self.framework_variant != "baseline" and random.random() < 0.05 and len(self.devices) > 1:
                    requestor = device
                    # Select a random partner that is not self and not in avoid_me list
                    potential_targets = [d for d in self.devices if d != requestor and not any(r.get('device')==requestor for r in d.relationships.get('avoid_me',[]))]
                    if potential_targets:
                        target_performer = random.choice(potential_targets)
                        # Lab sim: simple task like 'sense' or 'actuate' (even if device can't fully perform, it's an interaction)
                        requested_task = random.choice(target_performer.capabilities) if target_performer.capabilities else random.choice(['sense', 'actuate'])
                        load_for_task = random.randint(3,8)
                        # Details for the interaction
                        inter_device_details = {
                            'iot_app_reward': 0, # No direct reward for background pings
                            'is_background_task': True,
                            'simulated_command': 'PING_STATUS' # Example
                        }
                        if requested_task == 'transmit' and isinstance(target_performer, CommunicatingDevice):
                            inter_device_details['target_comm_device'] = target_performer # Target self for a simple comms check
                            inter_device_details['message'] = f"Lab background ping from {requestor.nameShort()}"


                        # Requestor (self) makes a request to target_performer
                        outcome = target_performer.handle_request(requestor, requested_task, load_for_task, inter_device_details)

                        # Requestor updates its trust in target_performer based on outcome
                        if 'measured_qos_for_requestor' in outcome: # This QoS is from target_performer's perspective
                            requestor.update_trust_from_qoe(target_performer, requested_task, outcome['measured_qos_for_requestor'], "requester")
                            # if outcome.get('success'):
                            #     self.logger.log_info("SIM_INTERACTION", f"{requestor.nameShort()} successful background '{requested_task}' with {target_performer.nameShort()}", context_override=self.run_context_name)


            # All devices reduce some load periodically
            device.reduce_load(random.randint(3,7))
            # Check minimum income satisfaction periodically
            if self.current_minute > 0 and self.current_minute % self.metrics['min_income_check_interval'] == 0:
                device.check_min_income_satisfied()

        # Fail PENDING jobs in the main queue that missed their deadline and weren't assigned
        pending_jobs_to_fail = [job for job in list(self.job_queue) if job.status == "PENDING" and self.current_minute > job.deadline_time and job.id not in active_jobs_this_cycle_ids]
        for job in pending_jobs_to_fail:
            job.status = "FAILED_DEADLINE_UNASSIGNED"
            self.metrics['jobs_failed_deadline'] += 1
            # No device to penalize directly if unassigned
            self.logger.log_info("JOB_FAIL_QUEUE", f"Job {job.id} FAILED DEADLINE (unassigned from queue).", context_override=self.run_context_name)
            self.failed_jobs.append(job)
            if job in self.job_queue: self.job_queue.remove(job)

        active_jobs_count = sum(1 for dev in self.devices if getattr(dev, 'current_job_id', None) is not None)
        self.logger.log_info("CYCLE_END", f"Minute: {self.current_minute} | Pending Jobs: {len(self.job_queue)} | Active Jobs on Devices: {active_jobs_count}", context_override=self.run_context_name)

    def run(self):
        self.setup_devices()
        for minute_cycle in range(self.time_frame):
            self.simulate_cycle(minute_cycle)
            # Log periodic summary
            if minute_cycle > 0 and (minute_cycle % (self.time_frame // 10 if self.time_frame >=10 else 1) == 0 or minute_cycle == self.time_frame -1) :
                 active_jobs_on_devices = sum(1 for dev in self.devices if getattr(dev, 'current_job_id', None) is not None)
                 failed_total = self.metrics['jobs_failed_deadline'] + self.metrics['jobs_failed_internal']
                 self.logger.log_info("PERIODIC_SUM", f"Min {minute_cycle} | Jobs (Pend/Act/Fail): {len(self.job_queue)}/{active_jobs_on_devices}/{failed_total} | Comp(OK/Late):{self.metrics['jobs_completed_on_time']}/{self.metrics['jobs_completed_late']}", context_override=self.run_context_name)
        self.report()

    def report(self):
        report_context_name = f"LabReport_{self.framework_variant}" # Use variant in report context
        self.logger.log_info("FINAL_REPORT_START", "\n" + "="*25 + f" LAB SIMULATION FINAL REPORT ({self.metrics['framework_mode_display']}) " + "="*25, context_override=report_context_name)

        total_completed = self.metrics['jobs_completed_on_time'] + self.metrics['jobs_completed_late']
        if total_completed > 0:
            completion_times = [job.completion_time - job.creation_time for job in self.completed_jobs if job.completion_time != -1 and job.creation_time != -1]
            self.metrics['avg_job_completion_time'] = sum(completion_times) / len(completion_times) if completion_times else 0

            late_jobs = [job for job in self.completed_jobs if job.status == "COMPLETED_LATE" and job.completion_time != -1 and job.deadline_time != -1]
            tardiness_values = [job.completion_time - job.deadline_time for job in late_jobs]
            self.metrics['avg_job_tardiness'] = sum(tardiness_values) / len(tardiness_values) if tardiness_values else 0

        self.metrics['final_total_balance_network'] = sum(d.balance for d in self.devices if hasattr(d, 'balance'))
        self.metrics['total_income_generated_network'] = sum(d.total_income_earned for d in self.devices if hasattr(d, 'total_income_earned'))

        avg_trust_value = "N/A (Baseline)"
        if self.framework_variant != "baseline" and self.devices:
            trust_scores = [d.trust_score for d in self.devices if hasattr(d, 'trust_score')]
            avg_trust_value = sum(trust_scores) / len(trust_scores) if trust_scores else "N/A (No trust scores)"
            self.metrics['avg_trust_at_end'] = avg_trust_value
        else:
            self.metrics['avg_trust_at_end'] = avg_trust_value


        avg_trust_display_string = f"{self.metrics['avg_trust_at_end']:.2f}" if isinstance(self.metrics['avg_trust_at_end'], float) else str(self.metrics['avg_trust_at_end'])

        summary_report_lines = [
            f"Framework Mode: {self.metrics['framework_mode_display']} (Variant: {self.framework_variant})",
            f"Duration: {self.time_frame}m | Devices: {self.num_devices}",
            "--- Job Statistics ---",
            f"Jobs Generated: {self.metrics['jobs_generated']}",
            f"Jobs Assigned: {self.metrics['jobs_assigned']}",
            f"Jobs Completed On Time: {self.metrics['jobs_completed_on_time']}",
            f"Jobs Completed Late: {self.metrics['jobs_completed_late']}",
            f"Jobs Failed Deadline (total): {self.metrics['jobs_failed_deadline']}",
            f"Total Work Units Processed: {self.metrics['total_work_units_processed']}",
            f"Avg Job Completion Time (for completed): {self.metrics['avg_job_completion_time']:.2f} min",
            f"Avg Job Tardiness (for late): {self.metrics['avg_job_tardiness']:.2f} min",
            "--- Device & Network Monetary & Trust ---",
            f"Total Rewards Earned by Devices (from jobs): {self.metrics['total_rewards_earned']:.0f}",
            f"Total Penalties Incurred by Devices (from jobs): {self.metrics['total_penalties_incurred']:.0f}",
            f"Final Total Network Balance (sum of device balances): {self.metrics['final_total_balance_network']:.0f}",
            f"Average Final Trust (Social Modes only): {avg_trust_display_string}",
            f"Misuse Incidents Detected: {self.metrics.get('misuse_incidents_detected', 'N/A')}",
            f"Successful Back-me Invocations: {self.metrics.get('back_me_invocations_successful', 'N/A')}"
        ]
        self.logger.log_info("OVERALL_SIM_SUMMARY", "\n".join(summary_report_lines), context_override=report_context_name)

        # Store metrics using the logger's central storage
        # The key should be consistent with how main.py expects to retrieve it for comparison
        # e.g., "lab_baseline", "lab_social_basic", "lab_full_siot"
        metrics_storage_key = f"lab_{self.framework_variant}"
        self.logger.store_simulation_metrics(
            simulation_run_key=metrics_storage_key,
            metrics_dict=self.metrics
        )
        self.logger.log_info("FINAL_REPORT_END", "="*70, context_override=report_context_name)

