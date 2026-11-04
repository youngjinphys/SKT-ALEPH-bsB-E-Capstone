/** Only presentation visuals use this clock. Input, IO and frame cadence stay real-time. */
export const PRESENTATION_MOTION_SCALE = 2;
export const PRESENTATION_MOTION_RATE = 1 / PRESENTATION_MOTION_SCALE;
export const presentationDuration = milliseconds => milliseconds * PRESENTATION_MOTION_SCALE;
export const SLIDE_TRANSITION_MS = presentationDuration(380);
