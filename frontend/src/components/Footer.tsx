import { Link } from "react-router-dom";

const Footer = () => {
  return (
    <footer className="border-t border-border py-12">
      <div className="container flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <span className="font-bold text-foreground">Vibe Testing</span>
          <span className="text-muted-foreground text-sm">Autonomous AI QA Agent</span>
        </div>
        <div className="flex items-center gap-6 text-sm text-muted-foreground">
          <span>Built for <span className="text-primary font-medium">Deep Agents Hackathon</span></span>
          <Link to="/pipeline" className="hover:text-foreground transition-colors">Pipeline</Link>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
