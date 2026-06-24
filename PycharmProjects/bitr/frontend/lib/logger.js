// Простое логирование для фронта

export const logger = {
  info: (event, data = {}) => {
    console.info(`[INFO] ${event}`, {
      ...data,
      timestamp: new Date().toISOString(),
    });
  },
  
  error: (event, data = {}) => {
    console.error(`[ERROR] ${event}`, {
      ...data,
      timestamp: new Date().toISOString(),
    });
  },
  
  warn: (event, data = {}) => {
    console.warn(`[WARN] ${event}`, {
      ...data,
      timestamp: new Date().toISOString(),
    });
  },
};

