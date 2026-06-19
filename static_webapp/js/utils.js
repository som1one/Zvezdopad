// js/utils.js

export function weightedRandom(sectorArray, weightTotal) {
    if (weightTotal <= 0 || !sectorArray || sectorArray.length === 0) {
        console.error("weightedRandom Error: Invalid input.");
        return -1;
    }
    let r = Math.random() * weightTotal;
    let w = 0;
    for (let i = 0; i < sectorArray.length; i++) {
        const currentWeight = sectorArray[i]?.weight ?? 0;
        if (currentWeight <= 0) continue;
        w += currentWeight;
        if (r < w) return i;
    }
    console.warn("weightedRandom fallback triggered.");
    for (let i = sectorArray.length - 1; i >= 0; i--) {
        if ((sectorArray[i]?.weight ?? 0) > 0) return i;
    }
    return -1;
}

export function randomInRange(min, max) {
  return Math.random() * (max - min) + min;
}

export function formatDateTime(timestampSeconds) {
    if (timestampSeconds === null || timestampSeconds === undefined) return 'N/A';
    try {
        const date = new Date(timestampSeconds * 1000);
        if (isNaN(date.getTime())) {
            console.warn(`Invalid timestamp received in formatDateTime: ${timestampSeconds}`);
            return 'Invalid Date';
        }
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${day}.${month}.${year} ${hours}:${minutes}`;
    } catch (e) {
        console.error("Error formatting date:", e);
        return 'Invalid Date';
    }
}

export function formatTimeLeft(totalSeconds) {
    if (totalSeconds === null || totalSeconds === undefined || totalSeconds < 0) {
        return "0 сек";
    }

    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = Math.floor(totalSeconds % 60);

    let result = "";
    if (hours > 0) {
        result += `${hours} ч `;
    }
    if (minutes > 0 || hours > 0) {
        result += `${minutes} мин `;
    }
    result += `${seconds} сек`;

    return result.trim();
}