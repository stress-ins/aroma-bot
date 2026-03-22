export interface FrameProps {
  /** Absolute path to the image file (PNG/JPG) */
  imagePath: string;
  /** Frame duration in seconds */
  duration: number;
  /** Text to overlay on the frame */
  overlayText: string;
  /** Ken Burns motion type: 0=zoom-in, 1=pan-LR, 2=zoom-out, 3=pan-RL */
  motionType: number;
}

export type TextAnimation = "fade" | "slide-up" | "typewriter" | "scale-in";

export interface AromaReelProps {
  frames: FrameProps[];
  /** Crossfade duration in seconds (default 0.5) */
  crossfadeDuration: number;
  /** Text animation style */
  textAnimation: TextAnimation;
  /** FPS (default 30) */
  fps: number;
}

export interface EducationalReelProps extends AromaReelProps {
  /** Show step numbers on frames */
  showStepNumbers: boolean;
  /** Show progress bar at bottom */
  showProgressBar: boolean;
}

export interface PromoReelProps extends AromaReelProps {
  /** Brand accent color (hex) */
  brandColor: string;
  /** CTA text for final frame */
  ctaText: string;
  /** Watermark image path */
  watermarkPath?: string;
}
