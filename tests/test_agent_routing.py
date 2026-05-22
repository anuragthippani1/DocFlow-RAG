from app.agent_router import agents_for_domain, detect_domain, skipped_agent_output


def test_research_pdf_skips_supply_chain_agents():
    sources = ["GRAIL — SLM-Enhanced Indexing for Agent Discovery.pdf"]
    domain = detect_domain(sources, "This paper discusses indexing for agent discovery.")
    flags = agents_for_domain(domain)

    assert domain == "research"
    assert flags["supplier"] is False
    assert flags["inventory"] is False
    assert flags["logistics"] is False
    assert flags["external_risk"] is True


def test_supply_chain_sources_enable_all_agents():
    sources = ["supplier-risk-report.pdf"]
    domain = detect_domain(sources, "Supplier lead times and inventory stockouts increased.")
    flags = agents_for_domain(domain)

    assert domain == "supply_chain"
    assert all(flags.values())


def test_skipped_agent_message_mentions_domain():
    output = skipped_agent_output("Supplier Agent", "research")
    assert "skipped" in output["reason"].lower()
    assert "research" in output["reason"].lower()
