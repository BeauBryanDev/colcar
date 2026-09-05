// types.ts 
export interface DefectDetection {
  id: string;
  part: string;
  defect: 'scratch' | 'crack' | 'dent' | 'scratch' | 'shatter_glass' | 'flat_tire';
  severity: 'bajo' | 'moderado' | 'grave';
  estimated_repair_cost: number;
  agent_diagnostic: string;
  // YOLOv11-seg provide nubmers like:  [x1, y1, x2, y2, ...]
  polygon_coordinates: number[]; 
}

export interface InspectionResponse {
  inspection_id: string;
  car_image_url: string;
  detections: DefectDetection[];
}
