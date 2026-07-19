/**
 * Typed API client for the Tea Packaging Optimization backend.
 *
 * All response types are inferred from the backend Pydantic schemas.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────

export interface SimulationInput {
  tea_density: number;
  package_weight: number;
  shipment_quantity: number;
  shipment_type: "total_weight" | "per_container";
  package_shape: "square" | "round";
  packaging_material: "paper" | "plastic" | "metal";
  target_market?: string;
}

export interface SimulationCreateResponse {
  id: string;
  status: string;
  message: string;
}

export interface PackageOption {
  id: string;
  simulation_id: string;
  /** The pouch's internal volume, cm³ (includes headspace). */
  volume_cm3: number;
  /** The tea's own volume (mass / density), cm³ — Module 3's "Product Volume". */
  product_volume_cm3: number;
  length_mm: number;
  width_mm: number;
  height_mm: number;
  shape: string;
  material: string;
  fill_ratio: number;
  /** Pouch material consumed per unit, in cm². */
  material_usage_cm2: number;
  cost_estimate: number;
  is_best: boolean;
  rank: number;
}

export interface CartonConfig {
  id: string;
  simulation_id: string;
  /** Outer dimensions — the spec you buy and palletise. */
  length_mm: number;
  width_mm: number;
  height_mm: number;
  /** Inner cavity the pouches actually pack into. */
  inner_length_mm: number;
  inner_width_mm: number;
  inner_height_mm: number;
  units_per_carton: number;
  arrangement: string | null;
  carton_weight_kg: number;
  board_grade: string;
  board_cost_per_carton: number | null;
}

export interface PalletConfig {
  id: string;
  simulation_id: string;
  cartons_per_layer: number;
  layers: number;
  cartons_per_pallet: number;
  pallet_height_m: number;
  total_weight_kg: number;
  layer_pattern: string | null;
  footprint_utilization_pct: number | null;
}

/**
 * Container loading result (Module 6).
 *
 * Metrics belong to one of two views and are named for it. `*_per_container`
 * describes one FULL container (the packing scheme); the rest describes THIS
 * order (what gets booked and paid for). They are different numbers — a one-pouch
 * order can pack densely yet utilise ~0% of the container it books.
 */
export interface ContainerConfig {
  id: string;
  simulation_id: string;
  container_type: string;
  pallets_per_container: number | null;
  pallet_stack: number | null;

  // Capacity view — one full container
  cartons_per_container: number;
  /** Pouches in one full container — Module 6's "Total Units". */
  units_per_container: number;
  /** Packing density of a FULL container. */
  capacity_utilization_pct: number;
  /** Unused volume in one full container — Module 6's "Empty Space". */
  empty_space_per_container_m3: number;

  // Shipment view — this order
  containers_needed: number;
  total_units_shipped: number;
  /** Share of BOOKED volume holding tea — what the freight bill reflects. */
  utilization_pct: number;
  empty_space_total_m3: number;

  payload_kg: number | null;
  freight_cost: number;
  is_best: boolean;
}

export interface CompareRow {
  parameter_name: string;
  current_value: number;
  ai_value: number;
  improvement_pct: number;
  unit: string;
  /** Why this line moved — the lever responsible, in plain English. */
  driver: string;
}

export interface CompareResponse {
  simulation_id?: string;
  rows: CompareRow[];
  packaging_cost_current: number;
  packaging_cost_ai: number;
  carton_cost_current: number;
  carton_cost_ai: number;
  freight_cost_current: number;
  freight_cost_ai: number;
  total_cost_current: number;
  total_cost_ai: number;
  total_savings: number;
  /** How the "current practice" figures were derived. */
  baseline_assumptions: string[];
  baseline_is_user_supplied: boolean;
}

export interface SimulationDetail {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  inputs: SimulationInput | null;
  best_package: PackageOption | null;
  package_alternatives: PackageOption[];
  carton: CartonConfig | null;
  pallet: PalletConfig | null;
  best_container: ContainerConfig | null;
  container_alternatives: ContainerConfig[];
  comparison: CompareResponse | null;
}

export interface SimulationListItem {
  id: string;
  status: string;
  tea_density: number | null;
  package_weight: number | null;
  shipment_quantity: number | null;
  total_cost: number | null;
  total_savings: number | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedSimulations {
  items: SimulationListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardData {
  total_simulations: number;
  total_savings: number;
  average_container_utilization: number;
  recent_simulations: SimulationListItem[];
}

export interface PackageOptimizeResponse {
  best_package: PackageOption;
  alternatives: PackageOption[];
}

export interface CartonOptimizeResponse {
  config: CartonConfig;
}

export interface PalletOptimizeResponse {
  config: PalletConfig;
}

export interface ContainerOptimizeResponse {
  best_container: ContainerConfig;
  alternatives: ContainerConfig[];
}

export interface CompareRequest {
  simulation_id?: string;
  ship_quantity: number;
  tea_density: number;
  package_weight: number;
  current_package_length_mm?: number;
  current_package_width_mm?: number;
  current_package_height_mm?: number;
  current_carton_length_mm?: number;
  current_carton_width_mm?: number;
  current_carton_height_mm?: number;
  current_units_per_carton?: number;
  current_cartons_per_pallet?: number;
  current_containers?: number;
  current_packaging_cost?: number;
  current_freight_cost?: number;
}

// ── Fetch helper ──────────────────────────────────────────────────────────────

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }

  return res.json();
}

// ── Public API ────────────────────────────────────────────────────────────────

export const api = {
  // Dashboard
  getDashboard: () =>
    request<DashboardData>("/api/dashboard"),

  // Simulations
  createSimulation: (input: SimulationInput) =>
    request<SimulationCreateResponse>("/api/simulation", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  listSimulations: (page = 1, pageSize = 20) =>
    request<PaginatedSimulations>(
      `/api/simulation?page=${page}&page_size=${pageSize}`
    ),

  getSimulation: (id: string) =>
    request<SimulationDetail>(`/api/simulation/${id}`),

  // Standalone optimizations
  optimizePackage: (input: {
    tea_density: number;
    package_weight: number;
    package_shape: string;
    packaging_material: string;
  }) =>
    request<PackageOptimizeResponse>("/api/optimize/package", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  optimizeCarton: (input: {
    package_length_mm: number;
    package_width_mm: number;
    package_height_mm: number;
    package_weight_g: number;
    shipment_quantity: number;
  }) =>
    request<CartonOptimizeResponse>("/api/optimize/carton", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  optimizePallet: (input: {
    carton_length_mm: number;
    carton_width_mm: number;
    carton_height_mm: number;
    carton_weight_kg: number;
  }) =>
    request<PalletOptimizeResponse>("/api/optimize/pallet", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  optimizeContainer: (input: {
    carton_length_mm: number;
    carton_width_mm: number;
    carton_height_mm: number;
    cartons_per_pallet: number;
    pallet_height_m: number;
    shipment_quantity: number;
    units_per_carton?: number;
  }) =>
    request<ContainerOptimizeResponse>("/api/optimize/container", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  compare: (input: CompareRequest) =>
    request<CompareResponse>("/api/compare", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  // AI Analysis
  getAIAnalysis: (simulationId: string) =>
    request<AIAnalysis>(`/api/simulation/${simulationId}/ai`),

  // AI Chat — proxied server-side; no API key ever reaches the browser.
  chat: (input: ChatRequest) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify(input),
    }),
};

// ── AI Types ──────────────────────────────────────────────────────────────────

export interface StageValidation {
  stage: string;
  status: "valid" | "warning" | "invalid" | "unknown";
  message: string;
}

export interface AIAnalysis {
  validations: StageValidation[];
  summary: string;
  error?: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  message: string;
  simulation_id?: string;
  history: ChatMessage[];
}

export interface ChatResponse {
  reply: string;
  /**
   * Tools the assistant invoked. Non-empty means the numbers in the reply were
   * computed by the optimiser rather than written by the model.
   */
  tool_calls: string[];
}

export const sendChatMessage = (input: ChatRequest) => api.chat(input);

// ── Reference data ────────────────────────────────────────────────────────────

export interface PackageWeightOption {
  grams: number;
  label: string;
  is_default: boolean;
}

export interface TeaDensityOption {
  tea_type: string;
  min_density: number;
  max_density: number;
  typical_density: number;
}

export interface MaterialOption {
  key: string;
  name: string;
  cost_per_sqm: number;
  eco_score: number;
}

export interface PackageTypeOption {
  key: string;
  name: string;
  description: string | null;
}

export interface ContainerSpecOption {
  container_type: string;
  name: string;
  volume_m3: number;
  max_payload_kg: number;
}

/**
 * Master data backing the form dropdowns.
 *
 * Fetched rather than hardcoded: the SKUs an exporter sells and the rates the
 * costing uses are business data, and they must not drift apart by living in two
 * places. The bounds travel with the options so the client validates against the
 * same limits the API enforces.
 */
export interface ReferenceData {
  package_weights: PackageWeightOption[];
  tea_densities: TeaDensityOption[];
  materials: MaterialOption[];
  package_types: PackageTypeOption[];
  containers: ContainerSpecOption[];
  min_package_weight_g: number;
  max_package_weight_g: number;
  min_tea_density: number;
  max_tea_density: number;
}

export const getReferenceData = () => request<ReferenceData>("/api/reference");

// ── Load plan (3D visualisation) ──────────────────────────────────────────────

export interface Placement {
  /** Millimetres from the lower-left corner of the containing area. */
  x: number;
  y: number;
  /** True when the item's length runs along the area's width. */
  rotated: boolean;
}

export interface BoxDims {
  length_mm: number;
  width_mm: number;
  height_mm: number;
}

/**
 * The real load plan, as computed by the optimiser.
 *
 * A recipe, not 1,400 positions: one pallet layer plus one container floor, with
 * repeat counts. The client composes the load by translation only — it must never
 * re-derive a packing, because for a `mixed` pattern it cannot.
 */
export interface LoadPlan {
  simulation_id: string;
  container_type: string;
  container: BoxDims;
  pallet: BoxDims;
  /** Height of the empty pallet deck; cartons start above this. */
  pallet_base_height_mm: number;
  /** Outer dimensions — what is actually stacked. */
  carton: BoxDims;

  /** Cartons in ONE pallet layer, in pallet coordinates. */
  carton_layer: Placement[];
  layers: number;
  layer_pattern: string;

  /** Pallets on the container floor, in container coordinates. */
  pallet_floor: Placement[];
  pallet_stack: number;

  cartons_per_container: number;
  pallets_per_container: number;
  capacity_utilization_pct: number;

  /** Containers this shipment books. 1..N-1 are identical full loads. */
  containers_needed: number;
  /** Cartons aboard the LAST container — usually short of a full load. */
  cartons_last_container: number;
}

export const getLoadPlan = (simulationId: string) =>
  request<LoadPlan>(`/api/simulation/${simulationId}/layout`);

// ── Maximum capacity ──────────────────────────────────────────────────────────

export interface MaxCapacityPackage {
  length_mm: number;
  width_mm: number;
  height_mm: number;
  volume_cm3: number;
  product_volume_cm3: number;
  fill_ratio: number;
  cost_estimate: number;
  shape: string;
  material: string;
}

export interface MaxCapacityCarton {
  outer_length_mm: number;
  outer_width_mm: number;
  outer_height_mm: number;
  units_per_carton: number;
  arrangement: string;
  carton_weight_kg: number;
  board_grade: string;
}

export interface MaxCapacityPallet {
  cartons_per_layer: number;
  layers: number;
  cartons_per_pallet: number;
  pallet_height_m: number;
  total_weight_kg: number;
  layer_pattern: string;
  footprint_utilization_pct: number;
}

/**
 * The most that fits in ONE container of this type.
 *
 * `max_units_per_container` compares fairly only *within* a type — a 40HC beats
 * a 20GP because it is a bigger box, not because it packs better.
 * `capacity_utilization_pct` is the cross-type measure.
 */
export interface MaxCapacityOption {
  container_type: string;
  is_recommended_type: boolean;
  max_cartons_per_container: number;
  max_units_per_container: number;
  max_tea_weight_kg: number;
  capacity_utilization_pct: number;
  pallets_per_container: number;
  pallet_stack: number;
  payload_kg: number;
  max_payload_kg: number;
  limited_by: string;
  package: MaxCapacityPackage;
  carton: MaxCapacityCarton;
  pallet: MaxCapacityPallet;
  total_cost_for_shipment: number;
}

export interface MaxCapacity {
  simulation_id: string;
  options: MaxCapacityOption[];
  absolute_max_container_type: string;
  absolute_max_units: number;
  absolute_max_cartons: number;
  absolute_max_tea_weight_kg: number;
  recommended_container_type: string;
  recommended_units_per_container: number;
  max_units_for_recommended_type: number;
  gain_pct: number;
  cost_delta: number;
  already_maximal: boolean;
  verdict: string;
  /**
   * 3D load plan for the max-packed container. Embedded rather than fetched
   * separately: the max configuration is recomputed, never stored, so a second
   * endpoint would have to re-run the whole search to rebuild the same recipes.
   */
  layout: LoadPlan;
}

export const getMaxCapacity = (simulationId: string) =>
  request<MaxCapacity>(`/api/simulation/${simulationId}/max-capacity`);
