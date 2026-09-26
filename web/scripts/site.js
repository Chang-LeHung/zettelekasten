/**
 * Landing page behaviour.
 *
 *   1. the hero composer demo — example prompts typed, answered, saved
 *   2. the product tour — scroll switches the whole window between three states
 *   3. the first run — the provider form fills itself in, then saves
 *   4. quiet reveals and a nav hairline
 *
 * Everything degrades to a complete page: without JavaScript the markup already
 * shows the example prompt, the reply, the card, and the provider form, and
 * reduced motion gets each end state immediately.
 */

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function typeInto(element, text, speed, isStale = () => false) {
  return new Promise((resolve) => {
    let index = 0;
    const step = () => {
      if (isStale()) {
        resolve();
        return;
      }
      element.textContent = text.slice(0, (index += 1));
      if (index >= text.length) {
        resolve();
        return;
      }
      setTimeout(step, speed);
    };
    step();
  });
}

/* ------------------------------------------------------------ hero demo */

const EXAMPLES = [
  'Create a card from this idea: local-first beats sync for personal notes.',
  'Turn these rough notes into a slide deck for a team lunch talk.',
  'Summarize this paper into an article, keep the citations.',
  'Draft a LaTeX paper about CRDT-based note sync.',
  '把这段想法整理成一张卡片，标签放 local-first。',
];

const REPLY = [
  'Saved as a draft card. I kept your phrasing for the claim and split the reasoning into one paragraph.',
  'Eight slides, cover page first. Each slide carries one idea and the deck exports to PDF from the preview.',
];

const typed = document.querySelector('[data-role="typed"]');
const caret = document.querySelector('[data-role="caret"]');
const composer = document.querySelector('[data-role="composer"]');
const prompt = document.querySelector('[data-role="prompt"]');
const replyLine1 = document.querySelector('[data-role="reply-line-1"]');
const replyLine2 = document.querySelector('[data-role="reply-line-2"]');
const replyBlock = document.querySelector('[data-role="reply"]');
const artifact = document.querySelector('[data-role="artifact"]');

/** Reduced motion: show one finished exchange and stop. */
function showStaticDemo() {
  // The composer keeps the example line — that is what the hero is showing.
  // No user bubble: the static frame would only repeat the same sentence.
  typed.textContent = EXAMPLES[0];
  replyLine1.textContent = REPLY[0];
  artifact.classList.add('is-shown');
  caret.classList.remove('is-on');
}

async function runDemo() {
  let index = 0;
  for (;;) {
    const example = EXAMPLES[index % EXAMPLES.length];
    const reply = REPLY[index % REPLY.length];

    artifact.classList.remove('is-shown');
    replyLine1.textContent = '';
    replyLine2.textContent = '';
    prompt.textContent = '';
    typed.textContent = '';
    caret.classList.add('is-on');

    await wait(500);
    await typeInto(typed, example, 26);
    await wait(700);

    // "Send": the typed line becomes the user's message and the reply streams.
    typed.textContent = '';
    caret.classList.remove('is-on');
    prompt.textContent = example;
    // Restart the rise so every send looks like it left the composer.
    prompt.classList.remove('is-entering');
    void prompt.offsetWidth;
    prompt.classList.add('is-entering');
    replyBlock?.classList.add('is-thinking');
    await wait(450);
    replyBlock?.classList.remove('is-thinking');
    await typeInto(replyLine1, reply, 12);
    await wait(200);
    artifact.classList.add('is-shown');
    await wait(4200);

    index += 1;
  }
}

if (typed && prompt && artifact) {
  if (reduceMotion.matches) showStaticDemo();
  else runDemo();

  // Focus styling is part of the story the hero tells; it is not a real input.
  composer?.addEventListener('pointerenter', () => composer.classList.add('is-focused'));
  composer?.addEventListener('pointerleave', () => composer.classList.remove('is-focused'));
}

/* ------------------------------------------------- product tour states */

const storyStage = document.querySelector('[data-step-stage]');
const storySteps = [...document.querySelectorAll('.story__steps li[data-step]')];
const storyTitle = document.querySelector('[data-frame-title]');
const storyInput = document.querySelector('[data-story-input]');
const storyPrompt = document.querySelector('[data-story-prompt]');
const storyReply = document.querySelector('[data-story-reply]');
const storyCaret = document.querySelector('[data-story-caret]');

// One entry per step: what the whole window shows while that step is being read.
const STEPS = {
  1: {
    view: 'workspace',
    title: 'AI workspace',
    input: 'Create a card from this idea: local-first beats sync for personal notes.',
    prompt: '',
    reply: '',
  },
  2: {
    view: 'workspace',
    title: 'AI workspace',
    input: '',
    prompt: 'Create a card from this idea: local-first beats sync for personal notes.',
    reply: 'Saved as a draft card. Nothing publishes until you say so.',
  },
  3: {
    view: 'library',
    title: 'Library',
    input: '',
    prompt: '',
    reply: '',
  },
};

if (storyStage && storySteps.length) {
  // Typing is cancellable: moving to another step must stop the previous run so
  // two strings never race into the same element.
  let typingToken = 0;
  const stale = (token) => () => token !== typingToken;

  const apply = (step) => {
    const state = STEPS[step] ?? STEPS[1];
    typingToken += 1;
    const token = typingToken;
    storyStage.dataset.phase = step;
    storyStage.dataset.view = state.view;
    if (storyTitle) storyTitle.textContent = state.title;
    if (storyPrompt) storyPrompt.textContent = state.prompt;
    if (storyReply) storyReply.textContent = state.reply;
    if (storyInput) storyInput.textContent = state.input;
    if (storyCaret) storyCaret.classList.toggle('is-on', step === '1' || step === '2');
    for (const item of storySteps) item.classList.toggle('is-active', item.dataset.step === step);

    if (reduceMotion.matches) return;
    // The first step is the sentence being typed; the second is the answer
    // streaming back, so both read as something happening rather than a state.
    if (step === '1' && storyInput) typeInto(storyInput, state.input, 26, stale(token));
    if (step === '2' && storyReply) {
      storyReply.textContent = '';
      setTimeout(() => {
        if (token === typingToken) typeInto(storyReply, state.reply, 16, stale(token));
      }, 260);
    }
  };

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) apply(entry.target.dataset.step);
      }
    },
    // A thin band in the middle of the viewport decides which step is current.
    { rootMargin: '-45% 0px -45% 0px' },
  );
  storySteps.forEach((step) => observer.observe(step));
  apply('1');
}

/* ------------------------------------------------------------ first run */

const setup = document.querySelector('[data-setup]');

if (setup) {
  const steps = [...setup.querySelectorAll('[data-setup-step]')];
  const chip = setup.querySelector('[data-setup-chip]');
  const title = setup.querySelector('[data-setup-title]');
  const slider = setup.querySelector('[data-setup-slider]');
  const temperature = setup.querySelector('[data-setup-temp]');
  const fields = [...setup.querySelectorAll('[data-setup-type]')];
  const window_ = setup.querySelector('.app--setup');
  const submit = setup.querySelector('[data-setup-save]');
  const cursor = setup.querySelector('[data-setup-cursor]');
  const phaseText = {
    1: { chip: 'No model yet', title: 'Settings' },
    2: { chip: 'Adding a provider', title: 'Settings · AI providers' },
    3: { chip: 'deepseek-chat · Medium', title: 'Settings · AI providers' },
  };

  let run = 0;

  const reset = () => {
    for (const field of fields) field.textContent = '';
    slider?.style.setProperty('--temp', '0%');
    if (temperature) temperature.textContent = '0.0';
  };

  const apply = (phase) => {
    setup.dataset.phase = phase;
    if (chip) chip.textContent = phaseText[phase].chip;
    if (title) title.textContent = phaseText[phase].title;
    for (const item of steps) item.classList.toggle('is-active', item.dataset.setupStep === phase);
  };

  const finish = () => {
    for (const field of fields) field.textContent = field.dataset.setupType;
    slider?.style.setProperty('--temp', '20%');
    if (temperature) temperature.textContent = '0.2';
    cursor?.classList.remove('is-visible');
    apply(3);
  };

  /** Park the pointer on the submit button, whatever the window's size is. */
  const aimCursorAt = (element) => {
    if (!cursor || !window_ || !element) return;
    const box = window_.getBoundingClientRect();
    const target = element.getBoundingClientRect();
    cursor.style.setProperty('--cursor-x', `${target.left - box.left + target.width / 2 - 2}px`);
    cursor.style.setProperty('--cursor-y', `${target.top - box.top + target.height / 2 - 2}px`);
  };

  const play = async () => {
    run += 1;
    const token = run;
    if (reduceMotion.matches) {
      finish();
      return;
    }
    reset();
    apply(1);
    await wait(700);
    if (token !== run) return;
    apply(2);
    // Each field is typed in turn, the way someone would actually fill it in.
    for (const field of fields) {
      await typeInto(field, field.dataset.setupType, 26, () => token !== run);
      await wait(170);
      if (token !== run) return;
    }
    await wait(240);
    if (token !== run) return;
    slider?.style.setProperty('--temp', '20%');
    if (temperature) temperature.textContent = '0.2';
    await wait(1100);
    if (token !== run) return;

    // The last beat: a pointer travels to "Add provider", clicks it, and the
    // form cross-fades into the saved provider entry.
    if (cursor && submit) {
      aimCursorAt(submit);
      cursor.classList.add('is-visible');
      await wait(520);
      if (token !== run) return;
      // Press: the pointer dips, the button sinks, and the burst fires.
      cursor.classList.add('is-clicking');
      cursor.classList.add('is-pressed');
      submit.classList.add('is-pressed');
      await wait(140);
      if (token !== run) return;
      cursor.classList.remove('is-pressed');
      await wait(180);
      if (token !== run) return;
      submit.classList.remove('is-pressed');
      await wait(260);
      if (token !== run) return;
      cursor.classList.remove('is-clicking');
    }
    apply(3);
    await wait(700);
    cursor?.classList.remove('is-visible');
  };

  if (reduceMotion.matches) {
    finish();
  } else {
    // Runs once, the first time the window is properly in view.
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        observer.disconnect();
        play();
      },
      { threshold: 0.35 },
    );
    observer.observe(setup);
    apply(1);
  }
}

/* --------------------------------------------------- staged reveals */

/* ------------------------------------------------- phone and schedule */

/** Play one timeline the first time its block is properly in view. */
function playOnce(element, timeline, threshold = 0.35) {
  if (!element) return;
  if (reduceMotion.matches) {
    timeline(true);
    return;
  }
  const observer = new IntersectionObserver(
    (entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      observer.disconnect();
      timeline(false);
    },
    { threshold },
  );
  observer.observe(element);
}

/* A phone talking to Zett: three rounds, then it starts over. */

const phone = document.querySelector('[data-phone]');

if (phone) {
  const thread = phone.querySelector('[data-phone-thread]');
  const status = phone.querySelector('[data-phone-status]');
  const link = phone.querySelector('[data-phone-link]');
  const agent = phone.querySelector('[data-phone-agent]');
  const working = phone.querySelector('[data-phone-working]');
  const tools = phone.querySelector('[data-phone-tools]');
  const saved = phone.querySelector('[data-phone-saved]');
  const resultTitle = phone.querySelector('[data-phone-result-title]');
  const resultMeta = phone.querySelector('[data-phone-result-meta]');
  const tagOut = phone.querySelector('[data-phone-tag-out]');
  const tagIn = phone.querySelector('[data-phone-tag-in]');

  // Three real exchanges, each with the tools the assistant would actually call.
  const ROUNDS = [
    {
      attachment: 'photo',
      message: 'Turn this whiteboard photo into a card.',
      out: 'photo + text',
      tools: ['create_artifact', 'create_tag', 'list_tags'],
      result: ['Card · draft', '2 tags · in your library'],
      reply: 'Saved as a draft card: “Three rules for a smaller sync layer”. Tagged sync and design.',
    },
    {
      attachment: 'voice',
      message: 'What did I save about sync this week?',
      out: 'voice note',
      tools: ['query_artifacts', 'list_tags'],
      result: ['3 results', 'filtered by tag sync'],
      reply: 'Three notes mention sync — the newest is the card you saved this morning.',
    },
    {
      attachment: 'file',
      message: 'Keep this paper and tag it research.',
      out: 'paper.pdf',
      tools: ['create_asset', 'create_tag'],
      result: ['Asset · crdt-survey.pdf', 'tagged research'],
      reply: 'Filed crdt-survey.pdf into this conversation and tagged it research.',
    },
  ];

  const ATTACHMENTS = {
    photo: '<span class="mini-phone__thumb"></span>',
    voice: '<span class="mini-phone__voice"><i></i>0:12</span>',
    file: '<span class="mini-phone__file">crdt-survey.pdf</span>',
  };

  let visible = reduceMotion.matches;

  /** One new exchange in the thread; the older ones scroll up out of the phone. */
  const appendRound = (round) => {
    const wrap = document.createElement('div');
    wrap.className = 'thread-round';
    wrap.innerHTML =
      '<div class="thread-round__inner">' +
      `<span class="mini-phone__sent">${ATTACHMENTS[round.attachment]}` +
      '<span class="mini-phone__text"></span><span class="caret"></span></span>' +
      '<span class="mini-phone__reply"><span></span></span></div>';
    thread.append(wrap);
    void wrap.offsetHeight;
    wrap.classList.add('is-on');
    return {
      wrap,
      text: wrap.querySelector('.mini-phone__text'),
      caret: wrap.querySelector('.caret'),
      reply: wrap.querySelector('.mini-phone__reply'),
      replyText: wrap.querySelector('.mini-phone__reply span'),
    };
  };

  const resetAgent = () => {
    tools.classList.remove('is-on');
    tools.replaceChildren();
    saved.classList.remove('is-on');
  };

  /**
   * One trip across the link.
   *
   * The comet follows the SVG curve by sampling it every frame, so the glow
   * rides the arc exactly at any width instead of sliding along a dashed line.
   */
  const trip = async (direction) => {
    const svg = link?.querySelector('svg');
    const curve = link?.querySelector('.bridge__curve');
    const comet = link?.querySelector('[data-phone-comet]');
    if (!link || !svg || !curve || !comet) return;

    link.classList.add('is-live', direction === 'out' ? 'is-out' : 'is-in');
    const box = svg.getBoundingClientRect();
    const scaleX = box.width / 160;
    const scaleY = box.height / 40;
    const length = curve.getTotalLength();
    const start = performance.now();

    await new Promise((resolve) => {
      const frame = (now) => {
        const t = Math.min((now - start) / 900, 1);
        const eased = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
        const distance = direction === 'out' ? eased * length : (1 - eased) * length;
        const point = curve.getPointAtLength(distance);
        const ahead = curve.getPointAtLength(
          Math.min(Math.max(distance + (direction === 'out' ? 2 : -2), 0), length),
        );
        const angle = (Math.atan2(ahead.y - point.y, ahead.x - point.x) * 180) / Math.PI;
        comet.style.transform = `translate(${point.x * scaleX}px, ${point.y * scaleY}px) rotate(${angle}deg)`;
        comet.style.opacity = t < 0.06 || t > 0.94 ? '0' : '1';
        if (t < 1) requestAnimationFrame(frame);
        else resolve();
      };
      requestAnimationFrame(frame);
    });

    comet.style.opacity = '0';
    link.classList.remove('is-out', 'is-in');
  };

  const waitVisible = async () => {
    while (!visible) await wait(400);
  };

  const playRound = async (round) => {
    const node = appendRound(round);
    status.classList.remove('is-on');
    await wait(160);
    node.caret.classList.add('is-on');
    await typeInto(node.text, round.message, 26);
    node.caret.classList.remove('is-on');

    tools.innerHTML = round.tools
      .map((name, index) => `<span class="chip${index === 2 ? ' chip--quiet' : ''}">${name}</span>`)
      .join('');
    if (tagOut) tagOut.textContent = round.out;

    await wait(300);
    await trip('out');
    agent.classList.add('is-working');
    working.classList.add('is-on');
    await wait(700);
    working.classList.remove('is-on');
    agent.classList.remove('is-working');

    tools.classList.add('is-on');
    await wait(700);
    resultTitle.textContent = round.result[0];
    resultMeta.textContent = round.result[1];
    saved.classList.add('is-on');
    await wait(450);

    await trip('in');
    node.reply.classList.add('is-on');
    await typeInto(node.replyText, round.reply, 16);
    if (tagIn) tagIn.textContent = round.result[0].toLowerCase().includes('asset') ? 'asset + tags' : 'card + tags';
    status.textContent = 'sent · delivered';
    status.classList.add('is-on');
  };

  const runLoop = async () => {
    for (;;) {
      for (const round of ROUNDS) {
        await waitVisible();
        await playRound(round);
        await wait(2200);
        resetAgent();
        if (reduceMotion.matches) return;
      }
      // Clear the thread and go again, so the demo keeps showing new exchanges.
      await waitVisible();
      await wait(1400);
      thread.classList.add('is-clearing');
      await wait(500);
      thread.replaceChildren();
      thread.classList.remove('is-clearing');
      status.classList.remove('is-on');
    }
  };

  if (reduceMotion.matches) {
    // Static: every exchange, complete, no motion.
    for (const round of ROUNDS) {
      const node = appendRound(round);
      node.text.textContent = round.message;
      node.replyText.textContent = round.reply;
      node.reply.classList.add('is-on');
    }
    status.textContent = 'sent · delivered';
    status.classList.add('is-on');
    tools.innerHTML = ROUNDS.at(-1).tools.map((name) => `<span class="chip">${name}</span>`).join('');
    tools.classList.add('is-on');
    resultTitle.textContent = ROUNDS.at(-1).result[0];
    resultMeta.textContent = ROUNDS.at(-1).result[1];
    saved.classList.add('is-on');
  } else {
    const observer = new IntersectionObserver(
      (entries) => {
        visible = entries.some((entry) => entry.isIntersecting);
      },
      { threshold: 0.3 },
    );
    observer.observe(phone);
    runLoop();
  }
}

/* Scriptable: Claude Code and Codex take turns filing into Zett. */

const relay = document.querySelector('[data-relay]');

if (relay) {
  const log = relay.querySelector('[data-relay-log]');
  const actor = relay.querySelector('[data-relay-actor]');

  // What each agent sends, and what lands in the library. No endpoints, no tool
  // names: this shows the outcome, the way the phone thread does.
  const AGENTS = [
    {
      id: 'claude',
      name: 'Claude Code',
      working: 'reading the branch…',
      done: 'filed',
      carried: 'branch summary',
      entry: ['Article · Release notes for 0.2', 'saved to the library · tagged release'],
    },
    {
      id: 'codex',
      name: 'Codex',
      working: 'uploading…',
      done: 'uploaded',
      carried: 'paper.pdf',
      entry: ['Asset · paper.pdf', '2.1 MB · referenced by the card'],
    },
  ];

  const agentEl = (id) => relay.querySelector(`[data-relay-agent="${id}"]`);
  const stateEl = (id) => relay.querySelector(`[data-relay-state="${id}"]`);

  /** Send one glowing packet along an agent's beam, like the phone thread. */
  const send = async (id) => {
    const link = relay.querySelector(`[data-relay-link="${id}"]`);
    const svg = link?.querySelector('svg');
    const curve = link?.querySelector('.bridge__curve');
    const comet = link?.querySelector('.bridge__comet');
    if (!link || !svg || !curve || !comet) return;

    link.classList.add('is-live', 'is-out');
    const box = svg.getBoundingClientRect();
    const scaleX = box.width / 160;
    const scaleY = box.height / 40;
    const length = curve.getTotalLength();
    const start = performance.now();

    await new Promise((resolve) => {
      const frame = (now) => {
        const t = Math.min((now - start) / 1200, 1);
        const eased = 1 - (1 - t) ** 3;
        const distance = eased * length;
        const point = curve.getPointAtLength(distance);
        const ahead = curve.getPointAtLength(Math.min(distance + 2, length));
        const angle = (Math.atan2(ahead.y - point.y, ahead.x - point.x) * 180) / Math.PI;
        comet.style.transform = `translate(${point.x * scaleX}px, ${point.y * scaleY}px) rotate(${angle}deg)`;
        comet.style.opacity = t < 0.06 || t > 0.94 ? '0' : '1';
        if (t < 1) requestAnimationFrame(frame);
        else resolve();
      };
      requestAnimationFrame(frame);
    });

    comet.style.opacity = '0';
    link.classList.remove('is-out');
    await wait(260);
    link.classList.remove('is-live');
  };

  /** Swap the actor line without it snapping from one name to the next. */
  const setActor = async (next) => {
    if (!actor || actor.textContent === next) return;
    actor.classList.add('is-swapping');
    await wait(440);
    actor.textContent = next;
    actor.classList.remove('is-swapping');
  };

  const addEntry = (agent) => {
    const item = document.createElement('li');
    item.innerHTML =
      '<div class="relay__log-row"><span class="relay__log-dot"></span>' +
      `<div class="relay__log-text"><strong>${agent.entry[0]}</strong>` +
      `<span>${agent.entry[1]}</span></div></div>`;
    log.append(item);
    // Force the collapsed layout to be recorded, otherwise the browser folds the
    // append and the class change into one frame and the growth never animates.
    void item.offsetHeight;
    item.classList.add('is-on');
  };

  const playAgent = async (agent) => {
    agentEl(agent.id)?.classList.add('is-active');
    const state = stateEl(agent.id);
    const tag = relay.querySelector(`[data-relay-link="${agent.id}"] [data-relay-tag]`);
    if (tag) tag.textContent = agent.carried;

    // Give the highlight, the label, and the beam time to land before anything
    // moves, and let each result sit on screen long enough to read.
    await setActor(agent.name);
    await wait(420);
    if (state) state.textContent = agent.working;
    await wait(820);

    await send(agent.id);

    addEntry(agent);
    await wait(1400);
    if (state) state.textContent = agent.done;

    await wait(3600);
    agentEl(agent.id)?.classList.remove('is-active');
  };

  const finish = () => {
    AGENTS.forEach((agent) => {
      addEntry(agent);
      const state = stateEl(agent.id);
      if (state) state.textContent = agent.done;
      const tag = relay.querySelector(`[data-relay-link="${agent.id}"] [data-relay-tag]`);
      if (tag) tag.textContent = agent.carried;
      actor.textContent = 'AI workspace';
    });
    if (actor) actor.textContent = 'AI workspace';
  };

  let visible = reduceMotion.matches;

  const runLoop = async () => {
    for (;;) {
      for (const agent of AGENTS) {
        while (!visible) await wait(400);
        await playAgent(agent);
      }
      while (!visible) await wait(400);
      await wait(3200);
      for (const item of [...log.children]) item.classList.remove('is-on');
      await wait(1300);
      log.replaceChildren();
      if (actor) actor.textContent = 'AI workspace';
    }
  };

  if (reduceMotion.matches) {
    finish();
  } else {
    const observer = new IntersectionObserver(
      (entries) => {
        visible = entries.some((entry) => entry.isIntersecting);
      },
      { threshold: 0.3 },
    );
    observer.observe(relay);
    runLoop();
  }
}

/* A scheduled run: pressed, executed, written to the library. */
const task = document.querySelector('[data-task]');

if (task) {
  const runButton = task.querySelector('[data-task-run]');
  const logSteps = [...task.querySelectorAll('[data-task-step]')];
  const result = task.querySelector('[data-task-result]');

  playOnce(task, async (instant) => {
    if (instant) {
      logSteps.forEach((step) => step.classList.add('is-on'));
      result.classList.add('is-on');
      return;
    }
    await wait(600);
    runButton?.classList.add('is-pressed');
    await wait(220);
    runButton?.classList.remove('is-pressed');
    for (const step of logSteps) {
      step.classList.add('is-on');
      await wait(760);
    }
    await wait(260);
    result.classList.add('is-on');
  });
}

// Cards in a staggered group wait for the group to arrive, then rise in order.
for (const group of document.querySelectorAll('[data-reveal-stagger]')) {
  [...group.children].forEach((child, index) => child.style.setProperty('--reveal-index', index));
}

/* ------------------------------------------------------------ reveals, nav */

const revealTargets = [...document.querySelectorAll('[data-reveal], [data-reveal-stagger]')];
if (reduceMotion.matches) {
  revealTargets.forEach((element) => element.classList.add('is-visible'));
} else {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add('is-visible');
        revealObserver.unobserve(entry.target);
      }
    },
    { rootMargin: '0px 0px -12% 0px', threshold: 0.15 },
  );
  revealTargets.forEach((element) => revealObserver.observe(element));
}

const nav = document.querySelector('.nav');
const onScroll = () => nav?.classList.toggle('is-scrolled', window.scrollY > 8);
onScroll();
window.addEventListener('scroll', onScroll, { passive: true });
