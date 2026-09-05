
import React, { useState } from 'react';
import { Stage, Layer, Image as KonvaImage, Line } from 'react-konva';
import useImage from 'use-image'; // npm install use-image (ayuda a cargar imágenes en Konva de forma reactiva)
import { InspectionResponse, DefectDetection } from './types';

// Colores de Tailwind traducidos a RGBA para los polígonos según el defecto
const DEFECT_COLORS: Record<string, string> = {
  scratch: 'rgba(234, 179, 8, 0.4)',      // Amarillo
  crack: 'rgba(239, 68, 68, 0.4)',        // Rojo
  dent: 'rgba(249, 115, 22, 0.4)',       // Naranja
  broken_lamp: 'rgba(168, 85, 247, 0.4)',      // Morado
  shatter_glass: 'rgba(59, 130, 246, 0.4)', // Azul
  flat_tire: 'rgba(75, 85, 99, 0.4)',      // Gris
};

interface CarInspectorVisualizerProps {
  data: InspectionResponse;
}

export const CarInspectorVisualizer: React.FC<CarInspectorVisualizerProps> = ({ data }) => {
  // Carga la foto original del carro inspeccionado
  const [carImage] = useImage(data.car_image_url);
  const [selectedDefect, setSelectedDefect] = useState<DefectDetection | null>(null);

  // Dimensiones del lienzo (puedes hacerlas dinámicas según la pantalla)
  const stageWidth = 800;
  const stageHeight = 500;

  return (
    <div className="flex flex-col lg:flex-row gap-6 p-6 bg-slate-900 min-h-screen text-white">
      {/* Contenedor del Gráfico de Inspección */}
      <div className="flex-1 bg-slate-800 rounded-xl p-4 border border-slate-700 shadow-xl overflow-hidden flex flex-col justify-center items-center">
        <h2 className="text-xl font-bold mb-4 self-start text-emerald-400">
          Mapa de Defectos Interactivos (YOLOv11)
        </h2>
        
        <div className="border border-slate-600 rounded-lg overflow-hidden bg-black">
          <Stage width={stageWidth} height={stageHeight}>
            <Layer>
              {/* Imagen del carro de fondo */}
              {carImage && (
                <KonvaImage 
                  image={carImage} 
                  width={stageWidth} 
                  height={stageHeight} 
                />
              )}

              {/* Polígonos de segmentación de YOLO */}
              {data.detections.map((detection) => (
                <Line
                  key={detection.id}
                  points={detection.polygon_coordinates}
                  fill={DEFECT_COLORS[detection.defect] || 'rgba(255,255,255,0.3)'}
                  stroke={detection.id === selectedDefect?.id ? '#ffffff' : 'transparent'}
                  strokeWidth={2}
                  closed={true} // Cierra el polígono uniendo el último punto con el primero
                  onClick={() => setSelectedDefect(detection)}
                  onTouchStart={() => setSelectedDefect(detection)}
                  // Cambia el cursor al pasar por encima del defecto
                  onMouseEnter={(e) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = 'pointer';
                  }}
                  onMouseLeave={(e) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = 'default';
                  }}
                />
              ))}
            </Layer>
          </Stage>
        </div>
        <p className="text-xs text-slate-400 mt-2">
          * Haz clic sobre las zonas resaltadas para ver el reporte de cotización.
        </p>
      </div>

      {/* Panel Lateral con Tailwind: Diagnóstico del Agente y Precios */}
      <div className="w-full lg:w-96 bg-slate-800 rounded-xl p-6 border border-slate-700 shadow-xl flex flex-col justify-between">
        <div>
          <h3 className="text-lg font-bold border-b border-slate-700 pb-3 text-slate-300">
            Detalle del Diagnóstico
          </h3>

          {selectedDefect ? (
            <div className="mt-4 space-y-4 animate-fade-in">
              <div>
                <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
                  Pieza Afectada
                </span>
                <p className="text-xl font-bold capitalize text-white">{selectedDefect.part}</p>
              </div>

              <div className="flex gap-4">
                <div>
                  <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
                    Defecto
                  </span>
                  <p className="text-sm font-semibold capitalize text-amber-400">{selectedDefect.defect}</p>
                </div>
                <div>
                  <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
                    Severidad
                  </span>
                  <span className={`block text-xs font-bold px-2 py-0.5 rounded mt-1 uppercase text-center ${
                    selectedDefect.severity === 'high' ? 'bg-red-500/20 text-red-400' :
                    selectedDefect.severity === 'medium' ? 'bg-amber-500/20 text-amber-400' :
                    'bg-emerald-500/20 text-emerald-400'
                  }`}>
                    {selectedDefect.severity}
                  </span>
                </div>
              </div>

              <div>
                <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
                  Análisis del Agente IA
                </span>
                <p className="text-sm text-slate-300 bg-slate-900/50 p-3 rounded-lg border border-slate-700/50 mt-1 italic">
                  "{selectedDefect.agent_diagnostic}"
                </p>
              </div>
            </div>
          ) : (
            <div className="h-48 flex items-center justify-center text-center text-slate-500 text-sm">
              Selecciona un defecto en el visualizador para cargar la información de reparación.
            </div>
          )}
        </div>

        {/* Bloque de Precios Dinámico */}
        <div className="mt-6 border-t border-slate-700 pt-4">
          <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
            Costo Estimado de Reparación
          </span>
          <div className="text-3xl font-black text-emerald-400 mt-1">
            {selectedDefect 
              ? `$${selectedDefect.estimated_repair_cost.toLocaleString('en-US', { minimumFractionDigits: 2 })} USD`
              : '$0.00 USD'
            }
          </div>
        </div>
      </div>
    </div>
  );
};

