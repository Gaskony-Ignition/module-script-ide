import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ConfigStrip from './ConfigStrip';

function renderStrip(editable: string[], attributes: Record<string, string | number | boolean> = {}) {
  const onChange = vi.fn();
  const onSave = vi.fn();
  const view = render(
    <ConfigStrip
      editable={editable}
      attributes={attributes}
      onChange={onChange}
      onSave={onSave}
      dirty
      readOnly={false}
    />
  );
  return { ...view, onChange, onSave };
}

describe('ConfigStrip', () => {
  it('renders nothing for a type whose attributes were never measured', () => {
    // Scheduled, tag-change, shutdown and update return an empty allowlist and
    // the server refuses every attribute write for them. Offering a control
    // would promise something the gateway will reject.
    const { container } = renderStrip([]);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders only the fields the server said are editable', () => {
    renderStrip(['enabled', 'delay', 'fixedDelay', 'sharedThread'], {
      enabled: true,
      delay: 5000,
      fixedDelay: false,
      sharedThread: true,
    });
    expect(screen.getByLabelText('Enabled')).toBeInTheDocument();
    expect(screen.getByLabelText('Delay (ms)')).toBeInTheDocument();
    expect(screen.getByLabelText('Fixed delay')).toBeInTheDocument();
    expect(screen.getByLabelText('Shared thread')).toBeInTheDocument();
    // A timer has no threadType and no hintScope — those belong to other types.
    expect(screen.queryByLabelText('Thread type')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Hint scope')).not.toBeInTheDocument();
  });

  it('offers exactly the two case-sensitive threadType values', () => {
    renderStrip(['enabled', 'threadType'], { enabled: true, threadType: 'Shared' });
    const select = screen.getByLabelText('Thread type') as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    // Case-sensitive and exhaustive: 'shared' is accepted by the resource layer
    // and then behaves wrongly, with nothing in any log to say so.
    expect(options).toEqual(['Shared', 'Dedicated']);
  });

  it('offers the four ApplicationScope hint scopes by their bitmask values', () => {
    renderStrip(['hintScope'], { hintScope: 7 });
    const select = screen.getByLabelText('Hint scope') as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toEqual(['0', '1', '2', '7']);
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
      'None',
      'Gateway',
      'Designer',
      'All',
    ]);
    expect(select.value).toBe('7');
  });

  it('reports a boolean for a checkbox and a number for a delay', () => {
    const { onChange } = renderStrip(['enabled', 'delay'], { enabled: false, delay: 1000 });
    fireEvent.click(screen.getByLabelText('Enabled'));
    fireEvent.change(screen.getByLabelText('Delay (ms)'), { target: { value: '2500' } });
    // The types are checked server-side, not coerced: a string "true" for a
    // boolean attribute is a 400.
    expect(onChange).toHaveBeenNthCalledWith(1, 'enabled', true);
    expect(onChange).toHaveBeenNthCalledWith(2, 'delay', 2500);
  });

  it('reports hintScope as a number, not the select element string', () => {
    const { onChange } = renderStrip(['hintScope'], { hintScope: 0 });
    fireEvent.change(screen.getByLabelText('Hint scope'), { target: { value: '1' } });
    expect(onChange).toHaveBeenCalledWith('hintScope', 1);
  });

  it('saves attributes through their own button, not the script save', () => {
    const { onSave } = renderStrip(['enabled'], { enabled: true });
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('disables saving when nothing changed, and every control when read-only', () => {
    const { rerender } = render(
      <ConfigStrip
        editable={['enabled', 'delay']}
        attributes={{ enabled: true, delay: 1000 }}
        onChange={vi.fn()}
        onSave={vi.fn()}
        dirty={false}
        readOnly={false}
      />
    );
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled();

    rerender(
      <ConfigStrip
        editable={['enabled', 'delay']}
        attributes={{ enabled: true, delay: 1000 }}
        onChange={vi.fn()}
        onSave={vi.fn()}
        dirty
        readOnly
      />
    );
    expect(screen.getByLabelText('Enabled')).toBeDisabled();
    expect(screen.getByLabelText('Delay (ms)')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled();
  });
});
