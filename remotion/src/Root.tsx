import { Composition } from "remotion";
import { AromaReel, aromaReelSchema } from "./compositions/AromaReel";
import { EducationalReel, educationalReelSchema } from "./compositions/EducationalReel";
import { PromoReel, promoReelSchema } from "./compositions/PromoReel";
import type { AromaReelProps, EducationalReelProps, PromoReelProps } from "./types";

const FPS = 30;
const WIDTH = 1080;
const HEIGHT = 1920;

function calcTotalFrames(props: AromaReelProps): number {
  const totalSeconds = props.frames.reduce((sum, f) => sum + f.duration, 0);
  const crossfadeOverlap =
    Math.max(0, props.frames.length - 1) * props.crossfadeDuration;
  return Math.ceil((totalSeconds - crossfadeOverlap) * (props.fps || FPS));
}

const defaultFrames = [
  {
    imagePath: "/placeholder.png",
    duration: 5,
    overlayText: "Aromatherapy",
    motionType: 0,
  },
];

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition<AromaReelProps>
        id="AromaReel"
        component={AromaReel}
        schema={aromaReelSchema}
        width={WIDTH}
        height={HEIGHT}
        fps={FPS}
        calculateMetadata={({ props }) => ({
          durationInFrames: calcTotalFrames(props),
        })}
        defaultProps={{
          frames: defaultFrames,
          crossfadeDuration: 0.5,
          textAnimation: "fade",
          fps: FPS,
        }}
      />
      <Composition<EducationalReelProps>
        id="EducationalReel"
        component={EducationalReel}
        schema={educationalReelSchema}
        width={WIDTH}
        height={HEIGHT}
        fps={FPS}
        calculateMetadata={({ props }) => ({
          durationInFrames: calcTotalFrames(props),
        })}
        defaultProps={{
          frames: defaultFrames,
          crossfadeDuration: 0.5,
          textAnimation: "slide-up",
          fps: FPS,
          showStepNumbers: true,
          showProgressBar: true,
        }}
      />
      <Composition<PromoReelProps>
        id="PromoReel"
        component={PromoReel}
        schema={promoReelSchema}
        width={WIDTH}
        height={HEIGHT}
        fps={FPS}
        calculateMetadata={({ props }) => ({
          durationInFrames: calcTotalFrames(props),
        })}
        defaultProps={{
          frames: defaultFrames,
          crossfadeDuration: 0.5,
          textAnimation: "fade",
          fps: FPS,
          brandColor: "#C4704B",
          ctaText: "Узнать больше",
        }}
      />
    </>
  );
};
