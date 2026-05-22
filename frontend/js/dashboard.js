const dashboardState = {
  totalQueries: 0,
  riskCounts: {
    Low: 0,
    Medium: 0,
    High: 0,
  },
  lastRisk: "—",
};

function dominantRisk() {
  const { Low, Medium, High } = dashboardState.riskCounts;
  if (High >= Low && High >= Medium && High > 0) return "High";
  if (Medium >= Low && Medium > 0) return "Medium";
  if (Low > 0) return "Low";
  return dashboardState.lastRisk;
}
