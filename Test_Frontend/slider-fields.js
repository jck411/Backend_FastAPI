const sliderRegistry = new WeakMap();

function resolveNumeric(value, fallback = NaN) {
  if (value === undefined || value === null || value === '') {
    return fallback;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function clampToRange(control, value) {
  let result = value;
  if (control.min !== '') {
    const min = Number(control.min);
    if (Number.isFinite(min)) {
      result = Math.max(result, min);
    }
  }
  if (control.max !== '') {
    const max = Number(control.max);
    if (Number.isFinite(max)) {
      result = Math.min(result, max);
    }
  }
  return result;
}

function getConfig(control) {
  return sliderRegistry.get(control) || null;
}

function isApproximately(value, target, tolerance) {
  if (!Number.isFinite(value) || !Number.isFinite(target)) {
    return false;
  }
  return Math.abs(value - target) <= tolerance;
}

function updateSliderDisplay(control) {
  const config = getConfig(control);
  if (!config) {
    return;
  }

  const numericValue = resolveNumeric(control.value, NaN);
  const isDefault = isApproximately(
    numericValue,
    config.defaultValue,
    config.tolerance,
  );

  const formatted = Number.isFinite(numericValue)
    ? config.format(numericValue)
    : '';

  if (config.display) {
    config.display.textContent = formatted;
  }

  const state = isDefault ? 'default' : 'custom';
  control.dataset.state = state;
  if (config.container) {
    config.container.dataset.state = state;
  }

  if (formatted) {
    control.title = formatted;
  } else {
    control.removeAttribute('title');
  }
}

function resolveDefaultValue(control, explicitDefault) {
  if (explicitDefault !== undefined && explicitDefault !== null) {
    const numeric = Number(explicitDefault);
    if (Number.isFinite(numeric)) {
      return clampToRange(control, numeric);
    }
  }

  const datasetValue = resolveNumeric(control.dataset.defaultValue, NaN);
  if (Number.isFinite(datasetValue)) {
    return clampToRange(control, datasetValue);
  }

  const min = resolveNumeric(control.min, NaN);
  if (Number.isFinite(min)) {
    return min;
  }

  return 0;
}

export function configureSlider(control, options = {}) {
  if (!control) {
    return;
  }

  if (sliderRegistry.has(control)) {
    updateSliderDisplay(control);
    return;
  }

  const id = control.id || options.id || '';
  const container =
    options.container ||
    (id ? control.closest(`[data-slider-field="${id}"]`) : control.closest('[data-slider-field]')) ||
    null;
  const display =
    options.display ||
    (container && id ? container.querySelector(`[data-slider-value="${id}"]`) : null) ||
    (id ? document.querySelector(`[data-slider-value="${id}"]`) : null);

  let format;
  if (typeof options.format === 'function') {
    format = options.format;
  } else {
    const maximumFractionDigits = options.maximumFractionDigits ?? 2;
    const minimumFractionDigits = options.minimumFractionDigits ?? maximumFractionDigits;
    const formatter = new Intl.NumberFormat(undefined, {
      minimumFractionDigits,
      maximumFractionDigits,
    });
    format = (value) => formatter.format(value);
  }

  const defaultValue = resolveDefaultValue(control, options.defaultValue);
  const stepValue = resolveNumeric(control.step, NaN);
  const tolerance = Number.isFinite(options.tolerance)
    ? Math.max(options.tolerance, 0)
    : Number.isFinite(stepValue) && stepValue > 0
      ? stepValue / 2
      : 1e-6;

  const config = {
    container,
    display,
    defaultValue,
    format,
    tolerance,
  };

  sliderRegistry.set(control, config);

  control.dataset.slider = 'true';
  control.value = String(defaultValue);

  const handleInput = () => {
    updateSliderDisplay(control);
  };

  control.addEventListener('input', handleInput);
  control.addEventListener('change', handleInput);

  updateSliderDisplay(control);
}

export function isSliderControl(control) {
  return sliderRegistry.has(control);
}

export function setSliderValue(control, value) {
  if (!control) {
    return;
  }

  const config = getConfig(control);
  if (!config) {
    if (value === undefined || value === null || value === '') {
      control.value = '';
    } else {
      control.value = String(value);
    }
    return;
  }

  const previousValue = control.value;

  if (value === undefined || value === null || value === '') {
    const numeric = clampToRange(control, config.defaultValue);
    control.value = String(numeric);
  } else {
    const numeric = resolveNumeric(value, NaN);
    if (Number.isFinite(numeric)) {
      control.value = String(clampToRange(control, numeric));
    } else {
      const fallback = clampToRange(control, config.defaultValue);
      control.value = String(fallback);
    }
  }

  updateSliderDisplay(control);

  if (control.value !== previousValue) {
    control.dispatchEvent(new Event('input', { bubbles: true }));
    control.dispatchEvent(new Event('change', { bubbles: true }));
  }
}

function parsePlainInput(control, integer = false) {
  const raw = control.value?.trim();
  if (!raw) {
    return null;
  }
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    return null;
  }
  if (!integer) {
    return value;
  }
  const intValue = Math.trunc(value);
  return Number.isFinite(intValue) ? intValue : null;
}

export function parseSliderValue(control, { integer = false } = {}) {
  if (!control) {
    return null;
  }

  const config = getConfig(control);
  if (!config) {
    return parsePlainInput(control, integer);
  }

  const numericValue = resolveNumeric(control.value, NaN);
  const isDefault = isApproximately(
    numericValue,
    config.defaultValue,
    config.tolerance,
  );
  if (isDefault) {
    return null;
  }

  if (!Number.isFinite(numericValue)) {
    return null;
  }

  if (!integer) {
    return numericValue;
  }

  const intValue = Math.trunc(numericValue);
  return Number.isFinite(intValue) ? intValue : null;
}

export function resetSlider(control) {
  setSliderValue(control, null);
}

export function refreshSliderDisplay(control) {
  if (!control) {
    return;
  }
  if (!getConfig(control)) {
    return;
  }
  updateSliderDisplay(control);
}
