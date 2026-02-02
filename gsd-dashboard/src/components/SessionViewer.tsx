import { useCallback, useEffect, useRef } from "react";
import type { FrameEvent, InputEvent } from "../lib/types";
import { domToSurface } from "../lib/coords";
import { InputCapture } from "./InputCapture";

interface SessionViewerProps {
  sessionId: string;
  frame: FrameEvent | null;
  connected: boolean;
  controlActive: boolean;
  onInput: (event: InputEvent) => void;
}

export function SessionViewer({
  sessionId,
  frame,
  connected,
  controlActive,
  onInput,
}: SessionViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const surfaceSize = useRef({ width: 1280, height: 720 });

  // Render frame to canvas
  useEffect(() => {
    if (!frame?.data_base64 || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      surfaceSize.current = { width: img.naturalWidth, height: img.naturalHeight };
      if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
      }
      ctx.drawImage(img, 0, 0);
    };
    img.src = `data:image/jpeg;base64,${frame.data_base64}`;
    imgRef.current = img;
  }, [frame]);

  const handleInput = useCallback(
    (type: InputEvent["type"], domX: number, domY: number, extra?: Partial<InputEvent>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const { x, y } = domToSurface(
        domX - rect.left,
        domY - rect.top,
        rect.width,
        rect.height,
        surfaceSize.current.width,
        surfaceSize.current.height,
      );

      onInput({ type, session_id: sessionId, x, y, ...extra });
    },
    [sessionId, onInput],
  );

  if (!connected) {
    return (
      <div className="flex h-full items-center justify-center bg-gray-900 text-gray-400">
        Connecting to session...
      </div>
    );
  }

  if (!frame) {
    return (
      <div className="flex h-full items-center justify-center bg-gray-900 text-gray-400">
        Waiting for frames...
      </div>
    );
  }

  return (
    <div className="relative flex h-full items-center justify-center bg-gray-900">
      <canvas
        ref={canvasRef}
        className="max-h-full max-w-full object-contain"
        style={{ imageRendering: "auto" }}
      />
      {controlActive && (
        <InputCapture
          canvasRef={canvasRef}
          onInput={handleInput}
          sessionId={sessionId}
          onRawInput={onInput}
        />
      )}
    </div>
  );
}
