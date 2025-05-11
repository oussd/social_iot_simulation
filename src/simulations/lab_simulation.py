import random
import time
import uuid # For unique job IDs
from collections import deque # For job queue

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
    def __init__(self, job_id, creation_time, work_units, deadline_time, base_reward, penalty_multiplier=1.5):
        self.id = job_id
        self.creation_time = creation_time
        self.work_units_required = work_units
        self.work_units_done = 0
        self.deadline_time = deadline_time # Absolute simulation time
        self.assigned_to_device_id = None
        self.status = "PENDING" # PENDING, ASSIGNED, IN_PROGRESS, COMPLETED_ON_TIME, COMPLETED_LATE, FAILED_DEADLINE
        self.completion_time = -1
        self.base_reward = base_reward
        self.penalty_for_failure = base_reward * penalty_multiplier

    def __repr__(self):
        return (f"Job(id={self.id}, wu={self.work_units_done}/{self.work_units_required}, "
                f"dl={self.deadline_time}, status={self.status}, assigned_to={self.assigned_to_device_id})")


class LabSimulation:
    def __init__(self, framework_enabled=True, num_devices=5, duration_minutes=240, logger_instance=None):
        self.framework_enabled = framework_enabled
        self.num_devices = num_devices
        self.devices = []
        self.time_frame = duration_minutes 
        
        if logger_instance:
            self.logger = logger_instance
        else:
            self.logger = SimulationLogger(simulation_name=f"LabSim_Framework{'ON' if framework_enabled else 'OFF'}")
        
        self.current_minute = 0

        # Job Management
        self.job_queue = deque()
        self.completed_jobs = []
        self.failed_jobs = []
        self.next_job_id_counter = 0
        self.job_generation_interval = 10 
        self.sudden_workload_chance = 0.05 

        # Metrics
        self.metrics = {
            'framework_mode': "SIoT_Framework_ENABLED" if framework_enabled else "Baseline_Framework_DISABLED",
            'jobs_generated': 0,
            'jobs_assigned':0,
            'jobs_completed_on_time': 0,
            'jobs_completed_late': 0,
            'jobs_failed_deadline': 0,
            'total_work_units_processed': 0,
            'avg_job_completion_time': 0, 
            'avg_job_tardiness': 0, 
            'device_cycles_working': {}, # Initialized in setup_devices
            'device_cycles_idle': {},   # Initialized in setup_devices
            'total_rewards_earned': 0,
            'total_penalties_incurred': 0,
            'qoe_interaction_samples': [], 
            'avg_trust_at_end': 0, # Will be updated correctly based on framework_enabled
            'final_total_balance_network': 0,
            'total_income_generated_network': 0,
            'min_income_check_interval': 30 
        }
        self.logger.log_info("SIM_INIT", f"Lab Simulation ({self.metrics['framework_mode']}) | Devices: {num_devices} | Duration: {self.time_frame}m", context_override=f"LabSim_Framework{'ON' if framework_enabled else 'OFF'}")

    def _get_next_job_id(self):
        self.next_job_id_counter += 1
        return f"job_{self.next_job_id_counter}"

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
                self.logger.log_info("JOB_GEN", f"New job: {job}")

        # Sudden workload
        if random.random() < self.sudden_workload_chance:
            num_sudden_jobs = random.randint(max(1,self.num_devices // 2), self.num_devices)
            self.logger.log_info("JOB_GEN", f"SUDDEN WORKLOAD: Generating {num_sudden_jobs} urgent jobs.")
            for _ in range(num_sudden_jobs):
                work = random.randint(10, 30) 
                deadline = self.current_minute + random.randint(work + 2, work + 15) 
                reward = work * random.randint(3,6) 
                job = Job(self._get_next_job_id(), self.current_minute, work, deadline, reward)
                self.job_queue.append(job)
                self.metrics['jobs_generated'] += 1
                self.logger.log_info("JOB_GEN", f"Urgent job: {job}")
                
    def setup_devices(self):
        device_types_counts = {'sensing': 0, 'actuating': 0, 'communicating': 0, 'composite': 0}
        base_starting_balance = 800
        min_income_per_period = 15
        
        # Initialize device-specific metrics keys
        for i in range(self.num_devices):
            dev_id_str = f"dev_{i+1}"
            self.metrics['device_cycles_working'][dev_id_str] = 0
            self.metrics['device_cycles_idle'][dev_id_str] = 0

        for i in range(self.num_devices):
            dev_id_str = f"dev_{i+1}" 
            dev_type_index = i % 4
            device_instance = None
            if dev_type_index == 0:
                device_instance = SensingDevice(dev_id_str, f"LabSensor{i+1}")
                device_types_counts['sensing'] += 1
            elif dev_type_index == 1:
                device_instance = ActuatingDevice(dev_id_str, f"LabActuator{i+1}")
                device_types_counts['actuating'] += 1
            elif dev_type_index == 2:
                device_instance = CommunicatingDevice(dev_id_str, f"LabComm{i+1}")
                device_types_counts['communicating'] += 1
            else:
                device_instance = CompositeDevice(dev_id_str, f"LabComposite{i+1}")
                device_types_counts['composite'] += 1
            
            if device_instance:
                device_instance.balance = base_starting_balance + random.randint(-50, 50)
                device_instance.min_acceptable_income_threshold = min_income_per_period + random.randint(-2, 2)
                self.devices.append(device_instance)
        
        self.logger.log_info("DEV_DIST", f"Total: {self.num_devices} | " + " | ".join([f"{k.capitalize()[:3]}:{v}" for k,v in device_types_counts.items()]))

        if self.framework_enabled:
            rel_counts = {'work_with_me': 0, 'back_me': 0, 'avoid_me': 0}
            for d1 in self.devices:
                for d2 in self.devices:
                    if d1 == d2: continue
                    if random.random() < 0.3: d1.add_relationship('work_with_me', d2); rel_counts['work_with_me'] +=1
                    if random.random() < 0.2: d1.add_relationship('back_me', d2); rel_counts['back_me'] +=1
                    if random.random() < 0.1: d1.avoid(d2); rel_counts['avoid_me'] +=1
            self.logger.log_info("REL_SETUP (Framework ON)", " | ".join([f"{k.capitalize()[:4]}:{v}" for k,v in rel_counts.items()]))
        else:
            self.logger.log_info("REL_SETUP (Framework OFF)", "No social relationships established.")


    def _assign_jobs_to_devices(self):
        idle_devices = [dev for dev in self.devices if not any(job.assigned_to_device_id == dev.device_id and job.status == "IN_PROGRESS" for job in self.completed_jobs + list(self.job_queue) + self.failed_jobs)]
        random.shuffle(idle_devices)

        for job in list(self.job_queue): # Iterate over a copy if modifying queue
            if job.status == "PENDING":
                if not idle_devices: break 

                assigned_device = None
                if self.framework_enabled:
                    if idle_devices:
                        # WITH FRAMEWORK: Could sort by trust, check capabilities, policies etc.
                        # For now, sort by trust score (higher is better) and assign to the most trusted idle device.
                        # Ensure devices have a trust_score attribute.
                        sorted_idle_devices = sorted(idle_devices, key=lambda d: getattr(d, 'trust_score', 0), reverse=True)
                        assigned_device = sorted_idle_devices.pop(0)
                else:
                    # WITHOUT FRAMEWORK: Simpler random assignment to an idle device
                    if idle_devices:
                        assigned_device = idle_devices.pop(0)
                
                if assigned_device:
                    job.assigned_to_device_id = assigned_device.device_id
                    job.status = "ASSIGNED" 
                    self.metrics['jobs_assigned'] += 1
                    self.logger.log_info("JOB_ASSIGN", f"Job {job.id} assigned to {assigned_device.nameShort()}")
            
    def simulate_cycle(self, minute):
        self.current_minute = minute
        self.logger.log_info("CYCLE_START", f"Minute: {self.current_minute} ({self.metrics['framework_mode']})")
        
        self._generate_jobs()
        self._assign_jobs_to_devices() 

        random.shuffle(self.devices) 

        for device in self.devices:
            current_device_job = None
            for job_in_queue in list(self.job_queue): 
                if job_in_queue.assigned_to_device_id == device.device_id and job_in_queue.status in ["ASSIGNED", "IN_PROGRESS"]:
                    current_device_job = job_in_queue
                    break
            
            if current_device_job:
                if current_device_job.status == "ASSIGNED":
                    current_device_job.status = "IN_PROGRESS"
                    self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} started Job {current_device_job.id}")
                
                work_done_this_cycle = 0
                if device.current_load < device.max_load * 0.85: 
                    if not device.consume_load(10): 
                         self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} on Job {current_device_job.id} could not consume load, no progress.")
                         self.metrics['device_cycles_idle'][device.device_id] +=1
                    else:
                        current_device_job.work_units_done += 1
                        self.metrics['total_work_units_processed'] += 1
                        work_done_this_cycle = 1
                        self.metrics['device_cycles_working'][device.device_id] +=1
                else:
                    self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} on Job {current_device_job.id} is overloaded (load: {device.current_load}), no progress.")
                    self.metrics['device_cycles_idle'][device.device_id] +=1 

                if work_done_this_cycle > 0:
                    self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} on Job {current_device_job.id}: {current_device_job.work_units_done}/{current_device_job.work_units_required} WU. Load: {device.current_load}")

                if current_device_job.work_units_done >= current_device_job.work_units_required:
                    current_device_job.completion_time = self.current_minute
                    if self.current_minute <= current_device_job.deadline_time:
                        current_device_job.status = "COMPLETED_ON_TIME"
                        self.metrics['jobs_completed_on_time'] += 1
                        device.receive_income(current_device_job.base_reward, f"Job {current_device_job.id} on time")
                        self.metrics['total_rewards_earned'] += current_device_job.base_reward
                        self.logger.log_info("JOB_COMPLETE", f"Job {current_device_job.id} COMPLETED ON TIME by {device.nameShort()}. Reward: {current_device_job.base_reward}")
                    else:
                        current_device_job.status = "COMPLETED_LATE"
                        self.metrics['jobs_completed_late'] += 1
                        reduced_reward = current_device_job.base_reward * 0.5 
                        device.receive_income(reduced_reward, f"Job {current_device_job.id} late")
                        self.metrics['total_rewards_earned'] += reduced_reward
                        self.logger.log_info("JOB_COMPLETE", f"Job {current_device_job.id} COMPLETED LATE by {device.nameShort()}. Reward: {reduced_reward}")
                    
                    self.completed_jobs.append(current_device_job)
                    if current_device_job in self.job_queue: self.job_queue.remove(current_device_job)
                
                elif self.current_minute > current_device_job.deadline_time: 
                    current_device_job.status = "FAILED_DEADLINE"
                    current_device_job.completion_time = self.current_minute 
                    self.metrics['jobs_failed_deadline'] += 1
                    device.receive_penalty(current_device_job.penalty_for_failure, "System", f"Job {current_device_job.id} missed deadline")
                    self.metrics['total_penalties_incurred'] += current_device_job.penalty_for_failure
                    self.logger.log_info("JOB_FAIL", f"Job {current_device_job.id} FAILED DEADLINE on {device.nameShort()}. Penalty: {current_device_job.penalty_for_failure}")
                    self.failed_jobs.append(current_device_job)
                    if current_device_job in self.job_queue: self.job_queue.remove(current_device_job)
            
            else: 
                 self.metrics['device_cycles_idle'][device.device_id] +=1
                 if self.framework_enabled and random.random() < 0.05 and len(self.devices) > 1: 
                    requestor = device
                    potential_targets = [d for d in self.devices if d != requestor and not any(r['device']==requestor for r in d.relationships.get('avoid_me',[]))]
                    if potential_targets:
                        target_performer = random.choice(potential_targets)
                        requested_task = random.choice(['sense', 'actuate']) 
                        load_for_task = random.randint(3,8)
                        inter_device_details = {'iot_app_reward': 0} 

                        outcome = target_performer.handle_request(requestor, requested_task, load_for_task, inter_device_details)
                        if 'measured_qos_for_requestor' in outcome:
                            requestor.update_trust_from_qoe(target_performer, requested_task, outcome['measured_qos_for_requestor'], "requester")
                            if outcome.get('success'): 
                                self.logger.log_info("SIM_INTERACTION", f"{requestor.nameShort()} successful background '{requested_task}' with {target_performer.nameShort()}")

            device.reduce_load(random.randint(3,7)) 
            if self.current_minute > 0 and self.current_minute % self.metrics['min_income_check_interval'] == 0:
                device.check_min_income_satisfied()

        pending_jobs_to_fail = [job for job in list(self.job_queue) if job.status == "PENDING" and self.current_minute > job.deadline_time]
        for job in pending_jobs_to_fail:
            job.status = "FAILED_DEADLINE_UNASSIGNED"
            self.metrics['jobs_failed_deadline'] += 1
            self.logger.log_info("JOB_FAIL", f"Job {job.id} FAILED DEADLINE (unassigned).")
            self.failed_jobs.append(job)
            if job in self.job_queue: self.job_queue.remove(job) 

        self.logger.log_info("CYCLE_END", f"Minute: {self.current_minute} | Pending Jobs: {len(self.job_queue)} | Active Jobs: {sum(1 for j in self.job_queue if j.status=='IN_PROGRESS')}")

    def run(self):
        self.setup_devices()
        for minute_cycle in range(self.time_frame):
            self.simulate_cycle(minute_cycle)
            if minute_cycle > 0 and (minute_cycle % (self.time_frame // 10 if self.time_frame >=10 else 1) == 0 or minute_cycle == self.time_frame -1) :
                 active_jobs_count = sum(1 for job_in_q in self.job_queue if job_in_q.status == "IN_PROGRESS")
                 self.logger.log_info("PERIODIC_SUM", f"Min {minute_cycle} | Jobs (Pend/Act/Fail): {len(self.job_queue)}/{active_jobs_count}/{len(self.failed_jobs)} | Comp(OK/Late):{self.metrics['jobs_completed_on_time']}/{self.metrics['jobs_completed_late']}")
        self.report()

    def report(self):
        self.logger.log_info("FINAL_REPORT_START", "\n" + "="*25 + f" LAB SIMULATION FINAL REPORT ({self.metrics['framework_mode']}) " + "="*25, context_override=f"LabReport_{self.metrics['framework_mode']}")
        
        total_completed = self.metrics['jobs_completed_on_time'] + self.metrics['jobs_completed_late']
        if total_completed > 0:
            completion_times = [job.completion_time - job.creation_time for job in self.completed_jobs if job.completion_time != -1 and job.creation_time != -1]
            self.metrics['avg_job_completion_time'] = sum(completion_times) / len(completion_times) if completion_times else 0
            
            late_jobs = [job for job in self.completed_jobs if job.status == "COMPLETED_LATE" and job.completion_time != -1 and job.deadline_time != -1]
            tardiness_values = [job.completion_time - job.deadline_time for job in late_jobs]
            self.metrics['avg_job_tardiness'] = sum(tardiness_values) / len(tardiness_values) if tardiness_values else 0
        
        self.metrics['final_total_balance_network'] = sum(d.balance for d in self.devices)
        self.metrics['total_income_generated_network'] = sum(d.total_income_earned for d in self.devices) 
        
        avg_trust_value = "N/A (Framework Disabled)"
        if self.framework_enabled and self.devices:
            avg_trust_value = sum(d.trust_score for d in self.devices) / len(self.devices)
            self.metrics['avg_trust_at_end'] = avg_trust_value # Store the float value
        else:
            self.metrics['avg_trust_at_end'] = avg_trust_value # Store "N/A" string

        # CORRECTED LINE: Conditional formatting for avg_trust_at_end
        avg_trust_display_string = f"{self.metrics['avg_trust_at_end']:.2f}" if isinstance(self.metrics['avg_trust_at_end'], float) else self.metrics['avg_trust_at_end']

        summary_report_lines = [
            f"Framework Mode: {self.metrics['framework_mode']}",
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
            "--- Device & Network Monetary ---",
            f"Total Rewards Earned by Devices (from jobs): {self.metrics['total_rewards_earned']:.0f}",
            f"Total Penalties Incurred by Devices (from jobs): {self.metrics['total_penalties_incurred']:.0f}",
            f"Final Total Network Balance (sum of device balances): {self.metrics['final_total_balance_network']:.0f}",
            f"Average Final Trust (Framework ON only): {avg_trust_display_string}",
        ]
        self.logger.log_info("OVERALL_SIM_SUMMARY", "\n".join(summary_report_lines), context_override=f"LabReport_{self.metrics['framework_mode']}")
        
        self.logger.store_simulation_metrics(
            simulation_run_key=f"lab_{'framework_on' if self.framework_enabled else 'framework_off'}", 
            metrics_dict=self.metrics 
        )
        self.logger.log_info("FINAL_REPORT_END", "="*70, context_override=f"LabReport_{self.metrics['framework_mode']}")
