import { Link, Route, Routes, useLocation } from "react-router-dom";
import { Component, lazy, Suspense, useEffect, type ReactNode } from "react";
import { Shell } from "./components/Shell";
import { EmptyState } from "./components/ui";
import { useJourney } from "./lib/store";
import { AdvisorChat, AdvisorForm } from "./pages/Advisor";
import { CheckoutPage } from "./pages/Checkout";
import { LanguageSelect, Landing, Onboarding } from "./pages/Entry";
import { ConsentPage, ResultPage, UploadPage } from "./pages/Kyc";
import { ConfirmationPage, OrdersPage, TrackerPage } from "./pages/Orders";
import { AddOnsPage, PlanPage, QuotePage } from "./pages/Plan";
import { CallbackPage, HelpPage, PrivacyPage } from "./pages/Support";
import { Spinner } from "./components/ui";

// Back office is code-split so customers on slow mobile networks never download charting code.
const OpsLeads = lazy(() => import("./pages/ops/Leads").then((m) => ({ default: m.OpsLeads })));
const OpsLogin = lazy(() => import("./pages/ops/OpsShell").then((m) => ({ default: m.OpsLogin })));
const OpsOverview = lazy(() => import("./pages/ops/Overview").then((m) => ({ default: m.OpsOverview })));
const work = () => import("./pages/ops/Work");
const OpsAudit = lazy(() => work().then((m) => ({ default: m.OpsAudit })));
const OpsCallbacks = lazy(() => work().then((m) => ({ default: m.OpsCallbacks })));
const OpsKycCase = lazy(() => work().then((m) => ({ default: m.OpsKycCase })));
const OpsKycQueue = lazy(() => work().then((m) => ({ default: m.OpsKycQueue })));
const OpsOrders = lazy(() => work().then((m) => ({ default: m.OpsOrders })));
const OpsPartners = lazy(() => work().then((m) => ({ default: m.OpsPartners })));

function NotFound() {
  const { t } = useJourney();
  return (
    <Shell>
      <EmptyState
        title={t("common.not_found")}
        action={
          <Link to="/" className="inline-flex min-h-12 items-center rounded-lg bg-brand px-5 font-semibold text-white hover:bg-brand-2">
            {t("common.home")}
          </Link>
        }
      >
        {t("common.not_found_sub")}
      </EmptyState>
    </Shell>
  );
}

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="mx-auto max-w-md p-6">
        <h1 className="text-[22px] font-bold">Something went wrong on this screen</h1>
        <p className="mt-2 text-ink-3">Your answers are saved in this tab. Reload to continue, or ask for a call-back.</p>
        <p className="mt-1 text-ink-3" lang="hi">आपके जवाब सेव हैं। पेज दोबारा लोड करें या कॉल-बैक माँगें।</p>
        <div className="mt-4 flex gap-3">
          <button className="min-h-12 rounded-lg bg-brand px-5 font-semibold text-white hover:bg-brand-2" onClick={() => window.location.reload()}>Reload</button>
          <a className="inline-flex min-h-12 items-center rounded-lg border border-control bg-white px-5 font-semibold hover:bg-mist" href="/help/callback">Call-back</a>
        </div>
      </div>
    );
  }
}

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    // newer browsers return a Promise from scrollTo; never hand that to React as a cleanup
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export default function App() {
  return (
    <ErrorBoundary>
      <ScrollToTop />
      <Suspense fallback={<div className="mx-auto max-w-5xl p-6"><Spinner label="Loading" /></div>}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/language" element={<LanguageSelect />} />
        <Route path="/start" element={<Onboarding />} />
        <Route path="/advisor" element={<AdvisorChat />} />
        <Route path="/advisor/form" element={<AdvisorForm />} />
        <Route path="/plan" element={<PlanPage />} />
        <Route path="/plan/add-ons" element={<AddOnsPage />} />
        <Route path="/quote" element={<QuotePage />} />
        <Route path="/checkout" element={<CheckoutPage />} />
        <Route path="/kyc/consent" element={<ConsentPage />} />
        <Route path="/kyc/upload" element={<UploadPage />} />
        <Route path="/kyc/result" element={<ResultPage />} />
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/orders/:id" element={<TrackerPage />} />
        <Route path="/orders/:id/confirmed" element={<ConfirmationPage />} />
        <Route path="/help" element={<HelpPage />} />
        <Route path="/help/callback" element={<CallbackPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/ops/login" element={<OpsLogin />} />
        <Route path="/ops" element={<OpsOverview />} />
        <Route path="/ops/leads" element={<OpsLeads />} />
        <Route path="/ops/kyc" element={<OpsKycQueue />} />
        <Route path="/ops/kyc/:id" element={<OpsKycCase />} />
        <Route path="/ops/orders" element={<OpsOrders />} />
        <Route path="/ops/partners" element={<OpsPartners />} />
        <Route path="/ops/callbacks" element={<OpsCallbacks />} />
        <Route path="/ops/audit" element={<OpsAudit />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
