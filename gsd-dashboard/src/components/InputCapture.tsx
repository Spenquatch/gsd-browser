import { useCallback, useEffect, type RefObject } from "react";
import type { InputEvent } from "../lib/types";

interface InputCaptureProps {
  canvasRef: RefObject<HTMLCanvasElement | null>;
  onInput: (
    type: InputEvent["type"],
    domX: number,
    domY: number,
    extra?: Partial<InputEvent>,
  ) => void;
  sessionId: string;
  onRawInput: (event: InputEvent) => void;
}

export function InputCapture({ canvasRef, onInput, sessionId, onRawInput }: InputCaptureProps) {
  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const button = e.button === 1 ? "middle" : e.button === 2 ? "right" : "left";
      onInput("click", e.clientX, e.clientY, { button });
    },
    [onInput],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      onInput("move", e.clientX, e.clientY);
    },
    [onInput],
  );

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      onInput("wheel", e.clientX, e.clientY, {
        delta_x: e.deltaX,
        delta_y: e.deltaY,
      });
    },
    [onInput],
  );

  // Keyboard events captured on the window when control is active
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!canvasRef.current) return;
      e.preventDefault();
      onRawInput({
        type: "keydown",
        session_id: sessionId,
        key: e.key,
      });
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (!canvasRef.current) return;
      e.preventDefault();
      onRawInput({
        type: "keyup",
        session_id: sessionId,
        key: e.key,
      });
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [canvasRef, sessionId, onRawInput]);

  return (
    <div
      className="absolute inset-0 cursor-crosshair"
      onClick={handleClick}
      onMouseMove={handleMouseMove}
      onWheel={handleWheel}
      onContextMenu={(e) => e.preventDefault()}
    />
  );
}
