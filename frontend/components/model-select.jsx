"use client";

import { useState } from "react";
import { healthLabel, modelOptionLabel, pricingLabel } from "../utils/model-info";

// The one shared model picker. Every screen that lets the user choose
// a synced provider model renders this component, so the option label
// (billing class, chat support, last real generation check) and the
// info line under the select are identical everywhere: Chat, Agent
// Studio, Compare, Code Analyzer, Projects and the Providers page.
// Works controlled (value + onChange) or uncontrolled (defaultValue,
// e.g. inside a FormData form via `name`).
export function ModelSelect({
  id,
  name,
  models = [],
  value,
  defaultValue = "",
  onChange,
  disabled = false,
  loading = false,
  placeholder,
  ariaLabel,
}) {
  const [inner, setInner] = useState(defaultValue);
  const current = value !== undefined ? value : inner;
  const selected = models.find((model) => model.id === current) || null;

  const handleChange = (event) => {
    if (value === undefined) setInner(event.target.value);
    onChange?.(event.target.value);
  };

  return (
    <div className="model-select-field">
      <select
        id={id}
        name={name}
        value={current}
        onChange={handleChange}
        disabled={disabled}
        aria-label={ariaLabel}
      >
        {placeholder !== undefined ? (
          <option value="">{placeholder}</option>
        ) : (
          models.length === 0 && (
            <option value="">{loading ? "Đang tải model…" : "Chưa có model chat"}</option>
          )
        )}
        {models.map((model) => (
          <option key={model.id} value={model.id}>
            {modelOptionLabel(model)}
          </option>
        ))}
      </select>
      {selected && (
        <p className="model-select-info">
          {pricingLabel(selected)} · {healthLabel(selected)}
        </p>
      )}
    </div>
  );
}
