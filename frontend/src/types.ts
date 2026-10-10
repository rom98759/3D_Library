export interface ListRef {
  id: number;
  name: string;
}

export interface ListSummary extends ListRef {
  model_count: number;
}

export interface Model {
  id: number;
  name: string;
  original_filename: string | null;
  path: string;
  source_archive: string | null;
  category: string | null;
  tags: string | null;
  size_x: number | null;
  size_y: number | null;
  size_z: number | null;
  volume: number | null;
  is_watertight: 0 | 1 | null;
  material: string | null;
  estimated_weight_g: number | null;
  estimated_print_time_h: number | null;
  thumbnail_path: string | null;
  added_at: string;
  print_count: number;
  deleted_at: string | null;
  printed: 0 | 1;
  lists: ListRef[];
  purge_at?: string; // uniquement sur /api/trash
}

export interface Stats {
  total_models: number;
  total_weight_g: number;
  total_print_time_h: number;
  trash_count: number;
  recent: Model[];
}

export type SortKey =
  | "added_desc"
  | "added_asc"
  | "name_asc"
  | "name_desc"
  | "weight_desc"
  | "weight_asc"
  | "volume_desc"
  | "volume_asc";

export interface ModelListParams {
  q?: string;
  lists?: number[];
  printed?: boolean;
  sort?: SortKey;
}

export type BatchActionKind =
  | "trash"
  | "restore"
  | "delete"
  | "add_list"
  | "remove_list"
  | "set_printed";

export interface BatchPayload {
  ids: number[];
  action: BatchActionKind;
  list_id?: number;
  printed?: boolean;
}

export interface ModelUpdatePayload {
  name?: string;
  category?: string;
  material?: string;
  tags?: string;
  source_archive?: string;
  printed?: boolean;
}
