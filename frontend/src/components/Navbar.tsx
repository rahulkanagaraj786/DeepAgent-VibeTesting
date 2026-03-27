import { Link } from "react-router-dom";
import { ExternalLink, Zap } from "lucide-react";

const Navbar = () => {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-xl">
      <div className="container flex h-16 items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 border border-primary/20">
            <Zap className="h-4 w-4 text-primary" />
          </div>
          <span className="text-lg font-bold tracking-tight text-foreground">Vibe Testing</span>
        </Link>

        <div className="hidden md:flex items-center gap-8">
          <Link to="/" className="text-sm text-muted-foreground hover:text-foreground transition-colors">Home</Link>
          <Link to="/pipeline" className="text-sm text-muted-foreground hover:text-foreground transition-colors">Pipeline</Link>
          <a href="#features" className="text-sm text-muted-foreground hover:text-foreground transition-colors">Features</a>
        </div>

        <div className="flex items-center gap-3">
          <span className="hidden sm:flex items-center gap-1.5 text-sm text-muted-foreground px-3 py-1.5 rounded-full border border-border">
            <span className="text-primary">✦</span> Deep Agents Hackathon
          </span>
          <Link
            to="/pipeline"
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Run Tests
            <ExternalLink className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
