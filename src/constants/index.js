import {
    mobile,
    backend,
    creator,
    web,
    javascript,
    typescript,
    html,
    css,
    reactjs,
    redux,
    tailwind,
    nodejs,
    mongodb,
    git,
    figma,
    docker,
    meta,
    starbucks,
    tesla,
    shopify,
    carrent,
    jobit,
    tripguide,
    threejs,
    dav,
    jnu,
    cold,
    jnu_placement,
    business,
    portfolio,
    yelpcamp,
    python,
    bootstrap,
    expressJS,
    c,
    cpp,
    reactrouter,
  } from "../assets";
  
  export const navLinks = [
    {
      id: "about",
      title: "About",
    },
    {
      id: "work",
      title: "Work",
    },
    {
      id: "contact",
      title: "Contact",
    },
  ];
  
  const services = [
    {
      title: "Web Developer",
      icon: web,
    },
    {
      title: "Backend Developer",
      icon: backend,
    },
  ];
  
  const technologies = [
    // {
    //   name: "HTML 5",
    //   icon: html,
    // },
    // {
    //   name: "CSS 3",
    //   icon: css,
    // },
    {
      name: "JavaScript",
      icon: javascript,
    },
    // {
    //   name: "TypeScript",
    //   icon: typescript,
    // },
    {
      name: "React JS",
      icon: reactjs,
    },
    {
      name: "Tailwind CSS",
      icon: tailwind,
    },
    {
      name: "Node JS",
      icon: nodejs,
    },
    {
      name: "MongoDB",
      icon: mongodb,
    },
    {
      name: "Three JS",
      icon: threejs,
    },
    {
      name: "git",
      icon: git,
    },
    // {
    //   name: "docker",
    //   icon: docker,
    // },
    {
      name: "python",
      icon: python,
    },
    // {
    //   name: "bootstrap",
    //   icon: bootstrap,
    // },
    // {
    //   name: "expressJS",
    //   icon: expressJS,
    // },
    {
      name: "C",
      icon: c,
    },
    {
      name: "C++",
      icon: cpp,
    },
    // {
    //   name: "react-router",
    //   icon: reactrouter,
    // }
  ];

  const educations = [
    {
      institution: "D.A.V. Model School, Durgapur",
      course: "AISSCE & SSC",
      date: "Apr 2011 - Aug 2021",
      icon: dav,
      iconBg: "#383E56",
      points: [
        "#3rd in AISSCE 2021"
      ]
    },
    {
      institution: "Jawaharlal Nehru University, New Delhi",
      course: "B.Tech in Computer Science and Engineering",
      date: "2021 - Present(~2025)",
      icon: jnu,
      iconBg: "#383E56",
      points: [
        "Executive"
      ]
    },

  ];
  
  const experiences = [
    {
      title: "Senior Executive",
      company_name: "Co.L.D. : The Computer Science Club of SoE JNU",
      icon: cold,
      iconBg: "#383E56",
      date: "Dec 2022 - Present",
      points: [
        "Executive at Co.L.D. - Computer Science Club of School of Engineering, Jawaharlal Nehru University",
      ],
    },
    {
      title: "Social Media Coordinator",
      company_name: "JNU Placement Cell",
      icon: jnu_placement,
      iconBg: "#E6DEDD",
      date: "Jan 2023 - Present",
      points: [
        "Social Media Coordinator at JNU Placement Cell",
      ],
    },
  ];
  
  const testimonials = [
    {
      testimonial:
        "I thought it was impossible to make a website as beautiful as our product, but Rick proved me wrong.",
      name: "Sara Lee",
      designation: "CFO",
      company: "Acme Co",
      image: "https://randomuser.me/api/portraits/women/4.jpg",
    },
    {
      testimonial:
        "I've never met a web developer who truly cares about their clients' success like Rick does.",
      name: "Chris Brown",
      designation: "COO",
      company: "DEF Corp",
      image: "https://randomuser.me/api/portraits/men/5.jpg",
    },
    {
      testimonial:
        "After Rick optimized our website, our traffic increased by 50%. We can't thank them enough!",
      name: "Lisa Wang",
      designation: "CTO",
      company: "456 Enterprises",
      image: "https://randomuser.me/api/portraits/women/6.jpg",
    },
  ];
  
  const projects = [
    {
      name: "Business Landing Page",
      description: "A responsive business landing page made with HTML CSS and Bootstrap.",
      tags: [
        {
          name: "HTML",
          color: "blue-text-gradient",
        },
        {
          name: "CSS",
          color: "green-text-gradient",
        },
        {
          name: "Bootstrap-css",
          color: "pink-text-gradient",
        },
      ],
      image: business,
      source_code_link: "https://github.com/tushar-c23/Business-Landing-Page",
    },
    {
      name: "Portfolio Website",
      description:
        "A responsive portfolio website made with React JS, Three JS, React-router and Tailwind CSS.",
      tags: [
        {
          name: "react",
          color: "blue-text-gradient",
        },
        {
          name: "react-router",
          color: "green-text-gradient",
        },
        {
          name: "ThreeJS",
          color: "pink-text-gradient",
        },
        {
          name: "TailwindCSS",
          color: "red-text-gradient",
        },
      ],
      image: portfolio,
      source_code_link: "https://github.com/tushar-c23/tushar-c23.github.io",
    },
    {
      name: "YelpCamp",
      description: "A responsive camp review web app with login and signup functionality which uses nodejs express and mongodb to store and fetch information.",
      tags: [
        {
          name: "Nodejs",
          color: "green-text-gradient",
        },
        {
          name: "Express",
          color: "red-text-gradient",
        },
        {
          name: "mongo",
          color: "pink-text-gradient",
        },
        {
          name: "ejs",
          color: "blue-text-gradient",
        },
      ],
      image: yelpcamp,
      source_code_link: "https://github.com/tushar-c23/YelpCamp",
    },
  ];
  
  export { services, educations, technologies, experiences, testimonials, projects };