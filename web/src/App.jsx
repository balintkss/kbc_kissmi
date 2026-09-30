import { useCallback, useEffect, useMemo, useState } from "react";
import { api, clearAccessToken, friendlyError, setAccessToken } from "./api.js";

const PERSONAS = [
  { id: 1, name: "Lotte", city: "Ghent", story: "Bought a car recently and wants to stay on track." },
  { id: 2, name: "Julien", city: "Namur", story: "A synthetic family scenario with customer confirmation." },
  { id: 3, name: "Emma", city: "Leuven", story: "Starting a first job and settling into a new home." },
  { id: 4, name: "Marc", city: "Antwerp", story: "Self-employed with a quiet month to plan for." },
  { id: 113, name: "Jens", city: "Ghent", story: "Needs support first; product offers are held back." },
];

const FACT_LABELS = {
  employment: "Work and income",
  income: "Income",
  has_car: "Car and mobility",
  housing: "Home",
  saves_monthly: "Saving habit",
  financial_buffer: "Financial buffer",
  subscriptions: "Recurring subscriptions",
  money_stress: "Plan needs attention",
  commutes_by_train: "Mobility",
  pet: "Household",
  life_event_new_car: "Recent change",
  life_event_moved: "Recent change",
  life_event_first_job: "Recent change",
  life_event_new_job: "Recent change",
};

const NAV = [
  ["home", "Today", "home"],
  ["product", "Explore", "compass"],
  ["twin", "Financial picture", "spark"],
  ["kate", "Ask Kate", "chat"],
];

function money(value, { signed = false } = {}) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const formatted = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 })
    .format(Math.abs(value));
  return signed && value < 0 ? `−${formatted}` : formatted;
}

function number(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 }).format(value)
    : "—";
}

function percent(value) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

function date(value) {
  if (typeof value !== "string") return value == null ? "" : String(value);
  const match = value.match(/^(before )?(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  const [, before = "", year, month, day] = match;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${before}${Number(day)} ${months[Number(month) - 1]} ${year}`;
}

function factValue(fact) {
  if (fact.value === true || fact.value === false || fact.value == null) return "";
  if (fact.key === "financial_buffer" && typeof fact.value === "number") return `${number(fact.value)} months`;
  if (["income", "saves_monthly", "childcare"].includes(fact.key) && typeof fact.value === "number") return `${money(fact.value)}/month`;
  if (Array.isArray(fact.value)) return fact.value.join(", ");
  return String(fact.value).replaceAll("_", " ");
}

function Icon({ name, size = 18 }) {
  const paths = {
    home: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5.5 9.5V21h13V9.5" /><path d="M9.5 21v-6h5v6" /></>,
    compass: <><circle cx="12" cy="12" r="8.5" /><path d="m15.5 8.5-2 5-5 2 2-5 5-2Z" /></>,
    spark: <><path d="m12 2 1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2Z" /><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z" /></>,
    chat: <><path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 9.3 9.3 0 0 1-3.7-.8L4 20l1.4-3.6A7.1 7.1 0 0 1 4 12a7.5 7.5 0 0 1 8-7.5 7.5 7.5 0 0 1 8 7Z" /><path d="M8 12h.01M12 12h.01M16 12h.01" /></>,
    shield: <><path d="M12 3 19 6v5c0 4.6-3 8-7 10-4-2-7-5.4-7-10V6l7-3Z" /><path d="m8.7 12 2.1 2.1 4.5-4.7" /></>,
    eye: <><path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="2.5" /></>,
    arrow: <><path d="M5 12h14" /><path d="m14 6 6 6-6 6" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    check: <path d="m5 12 4.2 4.2L19 6.5" />,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    calendar: <><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M8 3v4M16 3v4M4 10h16" /></>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>,
    warning: <><path d="m12 3 9 17H3L12 3Z" /><path d="M12 9v4M12 17h.01" /></>,
  };
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function App() {
  const [session, setSession] = useState(null);
  const [view, setView] = useState("home");
  const [topic, setTopic] = useState("car_insurance");
  const [topics, setTopics] = useState([]);
  const [data, setData] = useState(null);
  const [experience, setExperience] = useState(null);
  const [publicExperience, setPublicExperience] = useState(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const loadTopics = useCallback(async () => {
    const listed = await api("/topics", { auth: false });
    setTopics(listed);
    return listed;
  }, []);

  const loadPublicExperience = useCallback(async (nextTopic) => {
    const response = await api(`/experience/${encodeURIComponent(nextTopic)}?channel=web`, { auth: false });
    setPublicExperience(response);
    return response;
  }, []);

  const loadCustomer = useCallback(async (activeTopic = topic) => {
    const [me, moments, plan, twin, chat, nextExperience] = await Promise.all([
      api("/me"),
      api("/me/moments"),
      api("/me/plan"),
      api("/me/twin?with_evidence=true"),
      api("/me/chat"),
      api(`/experience/${encodeURIComponent(activeTopic)}?channel=app`),
    ]);
    setData({ me, moments, plan, twin, chat });
    setExperience(nextExperience);
  }, [topic]);

  const refresh = useCallback(async (activeTopic = topic) => {
    if (!session) return;
    setBusy(true);
    try {
      await Promise.all([loadCustomer(activeTopic), loadPublicExperience(activeTopic)]);
      setNotice("");
    } catch (error) {
      setNotice(friendlyError(error, "refresh your financial picture"));
    } finally {
      setBusy(false);
    }
  }, [loadCustomer, loadPublicExperience, session, topic]);

  useEffect(() => {
    loadTopics()
      .then(() => loadPublicExperience(topic))
      .catch((error) => setNotice(friendlyError(error, "load the product catalogue")));
  }, [loadPublicExperience, loadTopics, topic]);

  useEffect(() => {
    const onEnded = () => {
      setSession(null);
      setData(null);
      setExperience(null);
      setView("home");
      setNotice("Your session ended. Please sign in again.");
    };
    window.addEventListener("twin:session-ended", onEnded);
    return () => window.removeEventListener("twin:session-ended", onEnded);
  }, []);

  const selectTopic = async (nextTopic, targetView = "product") => {
    setTopic(nextTopic);
    setView(targetView);
    setBusy(true);
    try {
      const jobs = [loadPublicExperience(nextTopic)];
      if (session) jobs.push(loadCustomer(nextTopic));
      await Promise.all(jobs);
      setNotice("");
    } catch (error) {
      setNotice(friendlyError(error, "load this product"));
    } finally {
      setBusy(false);
    }
  };

  const signIn = async ({ customerId, password }) => {
    setBusy(true);
    setNotice("");
    try {
      const loggedIn = await api("/auth/login", { method: "POST", body: { customer_id: Number(customerId), password }, auth: false });
      setAccessToken(loggedIn.token);
      setSession({ expiresIn: loggedIn.expires_in });
      await Promise.all([loadTopics(), loadCustomer(topic), loadPublicExperience(topic)]);
      setView("home");
    } catch (error) {
      setNotice(error?.status === 401 ? "The customer ID or password is not recognised." : friendlyError(error, "sign in"));
      clearAccessToken();
      setSession(null);
    } finally {
      setBusy(false);
    }
  };

  const signOut = () => {
    clearAccessToken();
    setSession(null);
    setData(null);
    setExperience(null);
    setView("home");
    setNotice("You are signed out. Your session was not saved on this device.");
  };

  const giveFeedback = async (fact, correct, note) => {
    setBusy(true);
    try {
      await api(`/me/facts/${encodeURIComponent(fact)}/feedback`, { method: "POST", body: { correct, ...(note ? { note } : {}) } });
      await refresh(topic);
      setNotice(correct ? "Thanks — Kate+ will keep using this context." : "Removed from your recommendations and plan.");
    } catch (error) {
      setNotice(friendlyError(error, "update this fact"));
    } finally {
      setBusy(false);
    }
  };

  const sendChat = async (content) => {
    if (!content.trim() || busy || !data) return;
    const prior = data.chat.history || [];
    setBusy(true);
    setData((current) => ({ ...current, chat: { ...current.chat, history: [...prior, { role: "user", content }] } }));
    try {
      const result = await api("/me/chat", { method: "POST", body: { message: content } });
      setData((current) => ({
        ...current,
        chat: { ...current.chat, history: [...prior, { role: "user", content }, { role: "assistant", content: result.answer, tools_used: result.tools_used || [] }] },
      }));
    } catch (error) {
      setData((current) => ({ ...current, chat: { ...current.chat, history: prior } }));
      setNotice(friendlyError(error, "ask Kate"));
    } finally {
      setBusy(false);
    }
  };

  const main = useMemo(() => {
    if (!session || !data) return <PublicCatalogue experience={publicExperience} topics={topics} topic={topic} onTopic={selectTopic} busy={busy} />;
    if (view === "product") return <ProductComparison topic={topic} publicExperience={publicExperience} experience={experience} topics={topics} onTopic={selectTopic} busy={busy} />;
    if (view === "twin") return <FinancialPicture twin={data.twin} plan={data.plan} onFeedback={giveFeedback} busy={busy} />;
    if (view === "kate") return <Kate chat={data.chat} onSend={sendChat} busy={busy} />;
    return <Home me={data.me} moments={data.moments} plan={data.plan} topics={topics} onTopic={selectTopic} onView={setView} />;
  }, [busy, data, experience, publicExperience, session, topic, topics, view]);

  return (
    <div className="app-page">
      <Header session={session} me={data?.me} view={view} onView={setView} onSignOut={signOut} />
      {notice && <Notice text={notice} onDismiss={() => setNotice("")} />}
      {!session && <Login onSignIn={signIn} busy={busy} />}
      {session && data && <div className="signed-layout"><SideNav view={view} onView={setView} /><main className="app-main">{main}</main></div>}
      {!session && <main className="public-main">{main}</main>}
      <footer className="site-footer"><span>Kate+ concept prototype · synthetic data</span><span>Product wording is illustrative. Its Digital Twin memory is customer-controlled.</span></footer>
    </div>
  );
}

function Header({ session, me, view, onView, onSignOut }) {
  return <header className="topbar">
    <button className="brand" type="button" onClick={() => onView("home")} aria-label="Kate+ home">
      <span className="brand-mark"><i /><i /><i /></span>
      <span><b>Kate+</b><small>Financial context, in your control</small></span>
    </button>
    <div className="topbar-actions">
      {session ? <>
        <button className="quiet-action" type="button" onClick={() => onView("twin")}><Icon name="shield" size={16} /> Your control centre</button>
        <span className="profile-dot" aria-hidden="true">{me?.first_name?.slice(0, 1) || "•"}</span>
        <button className="signout" type="button" onClick={onSignOut}>Sign out</button>
      </> : <span className="trust-note"><Icon name="lock" size={15} /> Built for a safe synthetic demo</span>}
    </div>
  </header>;
}

function Notice({ text, onDismiss }) {
  return <div className="notice" role="status"><span>{text}</span><button type="button" onClick={onDismiss} aria-label="Dismiss message"><Icon name="close" size={16} /></button></div>;
}

function Login({ onSignIn, busy }) {
  const [customerId, setCustomerId] = useState("");
  const [password, setPassword] = useState("");
  const submit = (event) => { event.preventDefault(); if (customerId && password) onSignIn({ customerId, password }); };
  return <section className="entry">
    <div className="entry-copy">
      <p className="eyebrow">Kate+ · concept prototype</p>
      <h1>You shouldn’t have to explain your financial life twice.</h1>
      <p className="entry-lead">Kate+ turns customer-approved financial context into a calmer payday plan, one relevant next step and a clear explanation at every turn.</p>
      <div className="entry-principles">
        <span><Icon name="eye" /> See why Kate+ is acting</span>
        <span><Icon name="check" /> Correct what it gets wrong</span>
        <span><Icon name="shield" /> Help comes before selling</span>
      </div>
    </div>
    <div className="entry-panel">
      <div className="panel-intro"><p className="eyebrow">Demo access</p><h2>Choose a synthetic scenario</h2><p>Pick a situation, then enter its password from your local demo credentials file. Passwords are never shown or stored here.</p></div>
      <div className="persona-grid">
        {PERSONAS.map((persona) => <button type="button" className={`persona ${customerId === String(persona.id) ? "selected" : ""}`} key={persona.id} onClick={() => setCustomerId(String(persona.id))}>
          <span className="persona-name">{persona.name}<small>{persona.city}</small></span><span>{persona.story}</span>
        </button>)}
      </div>
      <form className="login-form" onSubmit={submit}>
        <label>Customer ID<input inputMode="numeric" pattern="[0-9]*" required value={customerId} onChange={(event) => setCustomerId(event.target.value.replace(/\D/g, ""))} placeholder="Choose a scenario above" /></label>
        <label>Password<input type="password" required value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="off" placeholder="Enter locally generated password" /></label>
        <button className="primary-button" type="submit" disabled={busy || !customerId || !password}>{busy ? "Connecting…" : "Open Kate+"}<Icon name="arrow" /></button>
      </form>
      <p className="login-foot"><Icon name="lock" size={15} /> Session stays in memory only. Nothing is saved in this browser.</p>
    </div>
  </section>;
}

function SideNav({ view, onView }) {
  return <nav className="side-nav" aria-label="Customer navigation">
    {NAV.map(([key, label, icon]) => <button type="button" key={key} className={view === key ? "active" : ""} onClick={() => onView(key)}><Icon name={icon} /><span>{label}</span></button>)}
    <a className="advisor-link" href="/ops"><span>Advisor view</span><Icon name="arrow" size={15} /></a>
  </nav>;
}

function Home({ me, moments, plan, topics, onTopic, onView }) {
  const primary = moments?.push?.[0];
  const secondary = moments?.push?.[1];
  const tight = typeof plan?.free_per_week === "number" && plan.free_per_week < 0;
  return <section className="home-view">
    <div className="home-head"><div><p className="eyebrow">Your private-banker preparation, at retail scale</p><h1>Good evening, {me?.first_name}.</h1><p>Your financial context is ready when you are.</p></div><button type="button" className="reason-button" onClick={() => onView("twin")}><Icon name="eye" size={16} /> What Kate+ remembers <Icon name="chevron" size={15} /></button></div>
    {tight && <SupportBanner onView={onView} />}
    <div className="home-grid">
      <PaydayPlan plan={plan} onView={onView} />
      <section className="trust-card"><div className="trust-card-top"><span className="fine-label">YOUR CONTROL</span><Icon name="shield" /></div><h2>Every recommendation has a reason.</h2><p>See the evidence, correct a fact, and Kate+ updates the plan across every channel.</p><button type="button" className="text-button" onClick={() => onView("twin")}>View financial picture <Icon name="arrow" size={15} /></button></section>
    </div>
    <section className="next-section"><div className="section-heading"><div><p className="eyebrow">Your next steps</p><h2>Useful, not noisy.</h2></div><span>{moments?.push?.length || 0} of 2 priority moments</span></div><div className="moment-grid">{primary && <MomentCard moment={primary} primary onTopic={onTopic} />}{secondary && <MomentCard moment={secondary} onTopic={onTopic} />}{!primary && <Empty label="Your plan has no urgent moments right now." />}</div></section>
    <section className="explore-section"><div className="section-heading"><div><p className="eyebrow">Explore the same catalogue, with context</p><h2>Start where it matters to you.</h2></div></div><div className="topic-row">{topics.map((item) => <button type="button" className="topic-button" key={item.id} onClick={() => onTopic(item.id)}><span>{item.title}</span><Icon name="arrow" size={16} /></button>)}</div></section>
  </section>;
}

function SupportBanner({ onView }) {
  return <aside className="support-banner"><Icon name="warning" /><div><b>Let’s make next month easier.</b><p>Your essential commitments need attention before any product offer. We’re keeping the focus on your plan.</p></div><button type="button" onClick={() => onView("home")}>See my plan</button></aside>;
}

function PaydayPlan({ plan, onView }) {
  if (!plan) return <section className="payday-card loading-card"><span className="fine-label">YOUR PLAN</span><h2>We’re preparing your financial picture.</h2></section>;
  const negative = plan.free_per_week < 0;
  return <section className={`payday-card ${negative ? "under-pressure" : ""}`}><div className="payday-meta"><span className="fine-label">YOUR NEXT PAYDAY</span><Icon name="calendar" /></div><h2>{plan.payday ? `${money(plan.income)} arrives ${date(plan.payday)}` : "Your quiet month plan"}</h2><p>{plan.income_note || "Bills, reserves and savings are considered before you spend."}</p><div className="plan-number"><span>{money(plan.free_per_week, { signed: true })}</span><small>{negative ? "short each week" : "free to spend each week"}</small></div><div className="plan-line"><span>Essential bills</span><b>{money(plan.bills_until_next_payday)}</b></div><div className="plan-line"><span>Set aside</span><b>{money(plan.reserve_total)}</b></div><button type="button" className="plan-link" onClick={() => onView("twin")}>See what shaped this plan <Icon name="arrow" size={15} /></button></section>;
}

function MomentCard({ moment, primary, onTopic }) {
  const topic = moment.topic;
  return <article className={`moment-card ${primary ? "primary" : ""} ${moment.sales ? "product-moment" : "help-moment"}`}><div className="moment-top"><span className="fine-label">{moment.sales ? "RELEVANT NEXT STEP" : "HELP FIRST"}</span>{moment.sales ? <Icon name="spark" /> : <Icon name="shield" />}</div><h3>{moment.title}</h3><p>{moment.body}</p>{topic ? <button type="button" onClick={() => onTopic(topic)}>{moment.sales ? "Explore the context" : "See the plan"}<Icon name="arrow" size={15} /></button> : <span className="plain-action">Your plan is ready <Icon name="check" size={15} /></span>}</article>;
}

function ProductComparison({ publicExperience, experience, topics, topic, onTopic, busy }) {
  const support = experience?.support_first;
  return <section className="product-view"><div className="product-head"><div><p className="eyebrow">One product engine, two experiences</p><h1>{publicExperience?.title || experience?.title || "Explore products"}</h1><p>A visitor sees the full catalogue. You see a useful next step, its reason and the alternatives.</p></div><TopicSelect topics={topics} selected={topic} onSelect={onTopic} /></div>{support && <aside className="support-banner"><Icon name="shield" /><div><b>We’re putting the plan before the product.</b><p>Your current financial picture needs attention, so Kate+ is not showing a product offer right now.</p></div></aside>}<div className="comparison-grid"><ExperiencePanel label="Visitor view" caption="All options, no customer context" experience={publicExperience} /><ExperiencePanel label="Your Kate+ view" caption="One best-fit next step, with the why" experience={experience} personalised busy={busy} /></div></section>;
}

function PublicCatalogue({ experience, topics, topic, onTopic, busy }) {
  return <section className="catalogue"><div className="catalogue-intro"><p className="eyebrow">Visitor view</p><h2>Explore the full catalogue.</h2><p>Sign in to see a customer-controlled financial context turn this into one relevant next step.</p></div><div className="catalogue-toolbar"><TopicSelect topics={topics} selected={topic} onSelect={onTopic} /><span><Icon name="eye" size={15} /> No personal context in this view</span></div><ExperiencePanel experience={experience} label="Available options" caption="Clear choices before a customer shares context" busy={busy} /></section>;
}

function TopicSelect({ topics, selected, onSelect }) {
  return <label className="topic-select">Explore <select value={selected} onChange={(event) => onSelect(event.target.value)}>{topics.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>;
}

function ExperiencePanel({ label, caption, experience, personalised, busy }) {
  const variants = experience?.variants || [];
  const alternatives = experience?.alternatives || [];
  const highlight = experience?.highlight;
  return <article className={`experience-panel ${personalised ? "personalised" : ""}`}><header><div><span className="view-tag">{label}</span><p>{caption}</p></div>{personalised && <span className="live-dot">Personalised</span>}</header>{busy && !experience ? <Empty label="Loading options…" /> : !experience ? <Empty label="The catalogue is unavailable. Start the local API to view it." /> : personalised && highlight ? <><section className={`best-fit ${highlight.id === "support" ? "support-fit" : ""}`}><span className="fine-label">{highlight.id === "support" ? "YOUR PLAN FIRST" : "BEST FIT FOR YOU"}</span><h2>{highlight.name}</h2><p>{highlight.summary}</p>{highlight.reason && <blockquote>{highlight.reason}</blockquote>}{highlight.because?.length > 0 && <details className="why-drawer"><summary><Icon name="eye" size={15} /> Why am I seeing this?</summary><div>{highlight.because.map((reason) => <ReasonChip key={reason.key} reason={reason} />)}</div></details>}<button type="button" className="primary-button" disabled>{highlight.id === "support" ? "See my plan" : "Start a KBC conversation"}<Icon name="arrow" /></button></section><AlternativeList items={alternatives} /></> : <div className="variant-grid">{variants.map((variant) => <VariantCard key={variant.id} variant={variant} />)}</div>}</article>;
}

function VariantCard({ variant }) {
  return <section className="variant"><h3>{variant.name}</h3><p>{variant.summary}</p>{variant.features?.length > 0 && <ul>{variant.features.map((feature) => <li key={feature}><Icon name="check" size={14} /> {feature}</li>)}</ul>}<button type="button" className="outline-button" disabled>Explore this option <Icon name="arrow" size={14} /></button></section>;
}

function AlternativeList({ items }) {
  if (!items?.length) return null;
  return <details className="alternatives"><summary>View {items.length} alternative{items.length === 1 ? "" : "s"}</summary><div>{items.map((item) => <section key={item.id}><h3>{item.name}</h3><p>{item.summary}</p></section>)}</div></details>;
}

function ReasonChip({ reason }) {
  return <div className="reason-chip"><span><Icon name="spark" size={14} /> {reason.summary}</span><b>{percent(reason.confidence)} confident</b></div>;
}

function FinancialPicture({ twin, plan, onFeedback, busy }) {
  const [openFact, setOpenFact] = useState(null);
  const [notes, setNotes] = useState({});
  const facts = twin?.facts || [];
  const groups = facts.reduce((all, fact) => {
    const group = fact.key.includes("car") || fact.key === "commutes_by_train" ? "Mobility" : fact.key.includes("home") || fact.key === "housing" || fact.key.includes("moved") ? "Home" : fact.key.includes("income") || fact.key.includes("employment") || fact.key.includes("buffer") || fact.key.includes("stress") || fact.key.includes("saves") ? "Plan and income" : "Other context";
    all[group] = [...(all[group] || []), fact];
    return all;
  }, {});
  return <section className="picture-view"><div className="picture-head"><div><p className="eyebrow">Your financial picture</p><h1>What Kate+ understands — and why.</h1><p>These are evidence-backed hypotheses, not a hidden profile. Correcting one updates the plan everywhere.</p></div><div className="picture-stamp"><Icon name="shield" /><span>Customer-controlled<br />financial memory</span></div></div>{plan?.adjusted_for_feedback?.length > 0 && <div className="updated-banner"><Icon name="check" /> Your weekly plan changed after your correction.</div>}{Object.entries(groups).map(([group, groupFacts]) => <section className="fact-group" key={group}><h2>{group}</h2><div className="fact-grid">{groupFacts.map((fact) => <FactCard key={fact.key} fact={fact} isOpen={openFact === fact.key} note={notes[fact.key] || ""} onOpen={() => setOpenFact(openFact === fact.key ? null : fact.key)} onNote={(value) => setNotes({ ...notes, [fact.key]: value })} onFeedback={onFeedback} busy={busy} />)}</div></section>)}{!facts.length && <Empty label="Your financial picture is loading…" />}</section>;
}

function FactCard({ fact, isOpen, note, onOpen, onNote, onFeedback, busy }) {
  const rejected = fact.rejected_by_customer;
  return <article className={`fact-card ${rejected ? "rejected" : ""}`}><header><div><span className="fine-label">{FACT_LABELS[fact.key] || fact.key.replaceAll("_", " ")}</span><h3>{factValue(fact)}</h3></div><span className="confidence">{percent(fact.confidence)}</span></header><p>{fact.summary}</p>{fact.since && <span className="since">Since {date(fact.since)}</span>}<div className="confidence-track"><span style={{ width: `${Math.round((fact.confidence || 0) * 100)}%` }} /></div>{fact.implies?.length > 0 && <div className="changes"><span>What this changes</span>{fact.implies.map((impact) => <p key={`${impact.cost}-${impact.monthly || impact.yearly}`}>• {impact.cost}: {impact.monthly ? `${money(impact.monthly)}/month` : `${money(impact.yearly)}/year`}</p>)}</div>}<button type="button" className="evidence-toggle" onClick={onOpen}>{isOpen ? "Hide supporting payments" : "See supporting payments"}<Icon name={isOpen ? "close" : "chevron"} size={15} /></button>{isOpen && <div className="evidence-list">{fact.evidence?.length ? fact.evidence.map((item) => <div key={item.tx_id}><span>{date(item.date)} · {item.counterparty}</span><b>{money(item.amount, { signed: true })}</b></div>) : <p>No transaction details are required for this context.</p>}</div>}<div className="feedback"><button type="button" className={fact.confirmed_by_customer ? "affirm active" : "affirm"} disabled={busy} onClick={() => onFeedback(fact.key, true)}><Icon name="check" size={14} /> That’s right</button><button type="button" className="reject" disabled={busy} onClick={() => onFeedback(fact.key, false, note)}><Icon name="close" size={14} /> That’s not me</button></div>{isOpen && <label className="note-field">Optional correction note<input maxLength="280" value={note} onChange={(event) => onNote(event.target.value)} placeholder="e.g. Sold it" /></label>}{rejected && <p className="removed-note">Not used in your recommendations or plan.</p>}</article>;
}

function Kate({ chat, onSend, busy }) {
  const [value, setValue] = useState("");
  const messages = chat?.history || [];
  const submit = (event) => { event.preventDefault(); if (value.trim()) { onSend(value.trim()); setValue(""); } };
  return <section className="kate-view"><div className="kate-head"><div className="kate-orb"><Icon name="spark" size={22} /></div><div><p className="eyebrow">Ask Kate+</p><h1>Useful answers, grounded in your plan.</h1><p>Kate+ checks the underlying financial tools before responding. She does not make the maths up.</p></div></div><div className="chat-shell"><div className="chat-status"><span><i /> Kate+ is ready</span><span>Grounded by your financial memory</span></div><div className="chat-body">{chat?.opener && <ChatBubble role="assistant" content={chat.opener.body} tools={[]} />}{messages.map((item, index) => <ChatBubble key={`${item.role}-${index}`} role={item.role} content={item.content} tools={item.tools_used || []} />)}{busy && <div className="typing" aria-label="Kate+ is responding"><i /><i /><i /></div>}</div><form className="chat-form" onSubmit={submit}><label className="sr-only" htmlFor="kate-message">Ask Kate+ a question</label><input id="kate-message" value={value} onChange={(event) => setValue(event.target.value)} maxLength="1000" disabled={busy} placeholder="Can I afford a €1,200 trip in August?" /><button type="submit" disabled={busy || !value.trim()}>Send <Icon name="arrow" size={16} /></button></form><p className="chat-guard"><Icon name="shield" size={14} /> General guidance only. A KBC adviser remains part of consequential decisions.</p></div></section>;
}

function ChatBubble({ role, content, tools }) {
  const labels = { payday_plan: "Kate checked your payday plan", check_affordability: "Kate checked affordability", spending_summary: "Kate checked your spending", recommend_product: "Kate checked your best-fit option" };
  return <div className={`bubble ${role}`}><p>{content}</p>{role === "assistant" && tools.map((tool, index) => <span className="tool-chip" key={`${tool.tool}-${index}`}><Icon name="check" size={13} /> {labels[tool.tool] || "Kate checked your plan"}</span>)}</div>;
}

function Empty({ label }) {
  return <div className="empty"><Icon name="spark" /><p>{label}</p></div>;
}

export default App;
