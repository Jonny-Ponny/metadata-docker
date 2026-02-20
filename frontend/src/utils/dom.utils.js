// src/utils/dom.utils.js

/**
 * Debounce function to limit how often a function is called
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
export function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Scroll an element into view with center alignment
 * @param {HTMLElement} element - Element to scroll to
 * @param {Object} options - Scroll options
 */
export function scrollToElement(element, options = {}) {
  if (!element) return;

  element.scrollIntoView({
    behavior: options.behavior || "smooth",
    block: options.block || "center",
    inline: options.inline || "nearest",
  });
}

/**
 * Equalize heights of multiple elements
 * @param {HTMLElement[]} elements - Array of elements to equalize
 * @returns {number} The maximum height applied
 */
export function equalizeElementHeights(elements) {
  const validElements = elements.filter((el) => el !== null);
  if (validElements.length === 0) return 0;

  // Reset heights to auto to get natural heights
  validElements.forEach((el) => {
    el.style.minHeight = "";
    el.style.height = "auto";
  });

  // Force reflow to ensure heights are calculated
  validElements.forEach((el) => void el.offsetHeight);

  // Get the maximum height
  const heights = validElements.map((el) => el.scrollHeight);
  const maxHeight = Math.max(...heights);

  // Apply the maximum height to all elements
  validElements.forEach((el) => {
    el.style.minHeight = `${maxHeight}px`;
    el.style.height = `${maxHeight}px`;
  });

  return maxHeight;
}
