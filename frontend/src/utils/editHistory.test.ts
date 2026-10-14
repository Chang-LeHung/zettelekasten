import { describe, expect, it } from 'vitest'
import { EditHistory, TYPING_WINDOW_MS, type EditSnapshot } from './editHistory'

const at = (text: string, block = 0, caret = text.length): EditSnapshot => ({ text, block, caret })

function history(start = 'a') {
  let time = 1_000
  const instance = new EditHistory(at(start), 200, () => time)
  return { instance, tick: (ms: number) => { time += ms } }
}

describe('edit history', () => {
  it('undoes and redoes whole steps', () => {
    const { instance } = history('a')
    instance.record(at('ab'), false)
    instance.record(at('abc'), false)

    expect(instance.undo()).toEqual(at('ab'))
    expect(instance.undo()).toEqual(at('a'))
    expect(instance.undo()).toBeNull()
    expect(instance.redo()).toEqual(at('ab'))
    expect(instance.redo()).toEqual(at('abc'))
    expect(instance.redo()).toBeNull()
  })

  it('folds quick typing in one block into one step', () => {
    const { instance, tick } = history('')
    for (const text of ['h', 'he', 'hel', 'hell', 'hello']) {
      instance.record(at(text), true)
      tick(100)
    }

    expect(instance.undo()).toEqual(at(''))
    expect(instance.canUndo).toBe(false)
  })

  it('starts a new step after a pause', () => {
    const { instance, tick } = history('')
    instance.record(at('one'), true)
    tick(TYPING_WINDOW_MS + 1)
    instance.record(at('one two'), true)

    expect(instance.undo()).toEqual(at('one'))
  })

  it('starts a new step when typing moves to another block', () => {
    const { instance, tick } = history('')
    instance.record(at('a\n\nb', 0), true)
    tick(50)
    instance.record(at('a\n\nbc', 1), true)

    expect(instance.undo()).toEqual(at('a\n\nb', 0))
  })

  it('never folds a structural change into typing', () => {
    const { instance, tick } = history('a')
    instance.record(at('ab'), true)
    tick(50)
    instance.record(at('ab\n\n', 1), false)
    tick(50)
    instance.record(at('ab\n\nc', 1), true)

    expect(instance.undo()).toEqual(at('ab\n\n', 1))
    expect(instance.undo()).toEqual(at('ab'))
  })

  it('drops the redo steps once something new is recorded', () => {
    const { instance } = history('a')
    instance.record(at('b'), false)
    instance.undo()
    instance.record(at('c'), false)

    expect(instance.canRedo).toBe(false)
  })

  it('does not record a change that changes nothing', () => {
    const { instance } = history('a')
    instance.record(at('a', 3, 0), false)

    expect(instance.canUndo).toBe(false)
  })

  it('ends a typing run when the caret moves away', () => {
    const { instance, tick } = history('')
    instance.record(at('a'), true)
    tick(50)
    instance.moveCaret(0, 0)
    tick(50)
    instance.record(at('ab'), true)

    expect(instance.undo()).toEqual(at('a', 0, 0))
  })

  it('keeps at most the configured number of steps', () => {
    const instance = new EditHistory(at('0'), 3)
    for (let step = 1; step <= 10; step += 1) instance.record(at(String(step)), false)

    let undone = 0
    while (instance.undo()) undone += 1
    expect(undone).toBe(3)
  })

  it('forgets everything on reset', () => {
    const { instance } = history('a')
    instance.record(at('b'), false)
    instance.reset(at('z'))

    expect(instance.canUndo).toBe(false)
    expect(instance.canRedo).toBe(false)
  })
})
