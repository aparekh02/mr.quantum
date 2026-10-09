// Types mirroring the trainer API contract (CONTRACTS.md C-13).

export interface DeviceInfo {
  name: string;
  title: string;
}

export interface SessionInfo {
  id: string;
  device: string;
  title: string;
  groups: Record<string, string[]>;
}

export interface PadInfo {
  name: string;
  pad_type: string;
  electrode_type: string;
  v_lower_bound: number | null;
  v_upper_bound: number | null;
  controllable: boolean;
  measurable: boolean;
  group: string | null;
}

export interface ParameterInfo {
  name: string;
  type: string;
  required: boolean;
  default: unknown;
}

export interface RoutineInfo {
  name: string;
  parameters: ParameterInfo[];
}

export type RunStatus = "running" | "succeeded" | "failed";

export interface RunInfo {
  id: string;
  routine: string;
  parameters: Record<string, unknown>;
  status: RunStatus;
  result: unknown;
  error: string | null;
  restored_voltages: boolean | null;
  first_seq: number;
  last_seq: number | null;
}

export type EventKind =
  | "run_started"
  | "run_finished"
  | "run_failed"
  | "sweep_point"
  | "sweep"
  | "measurement"
  | "analysis"
  | "voltages";

export interface TrainerEvent {
  seq: number;
  time: number;
  kind: EventKind;
  routine: string | null;
  name: string;
  data: unknown;
}

export type Voltages = Record<string, number>;

export interface LevelInfo {
  id: string;
  order: number;
  title: string;
  concept: string;
  objective: string;
  device: string;
  hint_count: number;
  measurement_budget: number;
}

export interface Evaluation {
  success: boolean;
  accuracy: number;
  score: number;
  measurements: number;
  feedback: string[];
}

export interface AttemptInfo {
  id: string;
  level_id: string;
  session_id: string;
  status: "active" | "submitted";
  measurements: number;
  hints_shown: number;
  evaluation: Evaluation | null;
}
