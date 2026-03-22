import React from "react";
import { Img, staticFile } from "remotion";
import { useKenBurns } from "../hooks/useKenBurns";

interface KenBurnsFrameProps {
  imagePath: string;
  motionType: number;
  startFrame: number;
  durationFrames: number;
}

export const KenBurnsFrame: React.FC<KenBurnsFrameProps> = ({
  imagePath,
  motionType,
  startFrame,
  durationFrames,
}) => {
  const { scale, translateX, translateY } = useKenBurns(
    motionType,
    startFrame,
    durationFrames
  );

  // Use staticFile for paths starting with /, otherwise use as-is (absolute paths)
  const src = imagePath.startsWith("/")
    ? staticFile(imagePath)
    : imagePath;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        overflow: "hidden",
        position: "absolute",
        top: 0,
        left: 0,
        backgroundColor: "#000",
      }}
    >
      <Img
        src={src}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale}) translate(${translateX}%, ${translateY}%)`,
          transformOrigin: "center center",
        }}
      />
    </div>
  );
};
