export const API_BASE_URL = "";
export const GET_STATE_ENDPOINT = `${API_BASE_URL}/api/get_user_state`;
export const START_SPIN_ENDPOINT = `${API_BASE_URL}/api/start_spin`;
export const CONFIRM_ACTION_ENDPOINT = `${API_BASE_URL}/api/confirm_spin_action`;
export const GET_GAME_HISTORY_ENDPOINT = `${API_BASE_URL}/api/get_game_history`;
export const PLAY_LUCK_GAME_ENDPOINT = `${API_BASE_URL}/api/play_luck_game`;
export const ATTEMPT_ROBBERY_ENDPOINT = `${API_BASE_URL}/api/attempt_robbery`;
export const PLAY_SLOTS_ENDPOINT = `${API_BASE_URL}/api/play_slots`;

export const items = [
    {"name": "Шампанское", "emoji": "🍾", "costNumber": 50, "distribution": { 25: 0.758, 50: 12.5, 100: 5.82 }, "canSell": true},
    {"name": "Кольцо", "emoji": "💍", "costNumber": 100, "distribution": { 25: 0.379, 50: 0.833, 100: 11.64 }, "canSell": true},
    {"name": "Свеча", "emoji": "🕯️", "costNumber": 350, "distribution": { 25: 0.758, 50: 1.67, 100: 5.47 }, "canSell": false},
    {"name": "100 Звезд", "emoji": "⭐", "costNumber": 100, "distribution": { 25: 0.379, 50: 0.833, 100: 11.64 }, "canSell": false},
    {"name": "Букет", "emoji": "💐", "costNumber": 50, "distribution": { 25: 0.758, 50: 12.5, 100: 5.82 }, "canSell": true},
    {"name": "Бриллиант", "emoji": "💎", "costNumber": 100, "distribution": { 25: 0.379, 50: 0.833, 100: 11.64 }, "canSell": true},
    {"name": "Ракета", "emoji": "🚀", "costNumber": 50, "distribution": { 25: 0.758, 50: 12.5, 100: 5.82 }, "canSell": true},
    {"name": "Сердце", "emoji": "💝", "costNumber": 15, "distribution": { 25: 22.35, 50: 8.09, 100: 3.49 }, "canSell": true},
    {"name": "Мишка", "emoji": "🧸", "costNumber": 15, "distribution": { 25: 22.35, 50: 8.09, 100: 3.49 }, "canSell": true},
    {"name": "Подарок", "emoji": "🎁", "costNumber": 25, "distribution": { 25: 25.0, 50: 13.49, 100: 5.82 }, "canSell": true},
    {"name": "Кубок", "emoji": "🏆", "costNumber": 100, "distribution": { 25: 0.379, 50: 0.833, 100: 11.64 }, "canSell": true},
    {"name": "Роза", "emoji": "🌹", "costNumber": 25, "distribution": { 25: 25.0, 50: 13.49, 100: 5.82 }, "canSell": true},
    {"name": "Торт", "emoji": "🎂", "costNumber": 50, "distribution": { 25: 0.758, 50: 12.5, 100: 5.82 }, "canSell": true}
];

export const mainColorPairs = [
    { color1: "#8f9fff", color2: "#ff8a9a" }, { color1: "#a1e0fc", color2: "#5bc6f8" },
    { color1: "#c5e1a5", color2: "#9ccc65" }, { color1: "#ffcc80", color2: "#ffb74d" },
    { color1: "#ffab91", color2: "#ff8a65" }, { color1: "#ce93d8", color2: "#ba68c8" },
    { color1: "#f48fb1", color2: "#f06292" }
];

export const FREE_SPIN_COOLDOWN_SECONDS = 86400;
export const SPIN_DURATION_MS = 5000;
export const WINDUP_DURATION_S = 0.2;
export const WINDUP_ANGLE = -10;
export const SPIN_SOUND_DELAY_MS = 200;
export const RESET_DELAY_MS = 300;

export const SPIN_SOUND_SRC = "sounds/spin-sound.mp3";
export const WIN_SOUND_SRC = "sounds/win-sound.mp3";

export const DEFAULT_SPIN_COST = 25;

export const PREFERENCE_STORAGE_KEY = "wheelPrizeActionPref";