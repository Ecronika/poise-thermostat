/* poise-card 0.54.0 — bundled, served by the Poise integration (ADR-0040) */
var K=globalThis,W=K.ShadowRoot&&(K.ShadyCSS===void 0||K.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Y=Symbol(),dt=new WeakMap,U=class{constructor(t,e,s){if(this._$cssResult$=!0,s!==Y)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o,e=this.t;if(W&&t===void 0){let s=e!==void 0&&e.length===1;s&&(t=dt.get(e)),t===void 0&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),s&&dt.set(e,t))}return t}toString(){return this.cssText}},ut=i=>new U(typeof i=="string"?i:i+"",void 0,Y),H=(i,...t)=>{let e=i.length===1?i[0]:t.reduce((s,n,o)=>s+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(n)+i[o+1],i[0]);return new U(e,i,Y)},mt=(i,t)=>{if(W)i.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of t){let s=document.createElement("style"),n=K.litNonce;n!==void 0&&s.setAttribute("nonce",n),s.textContent=e.cssText,i.appendChild(s)}},Q=W?i=>i:i=>i instanceof CSSStyleSheet?(t=>{let e="";for(let s of t.cssRules)e+=s.cssText;return ut(e)})(i):i;var{is:Ot,defineProperty:Nt,getOwnPropertyDescriptor:zt,getOwnPropertyNames:Dt,getOwnPropertySymbols:Ft,getPrototypeOf:It}=Object,q=globalThis,ft=q.trustedTypes,Lt=ft?ft.emptyScript:"",Bt=q.reactiveElementPolyfillSupport,T=(i,t)=>i,tt={toAttribute(i,t){switch(t){case Boolean:i=i?Lt:null;break;case Object:case Array:i=i==null?i:JSON.stringify(i)}return i},fromAttribute(i,t){let e=i;switch(t){case Boolean:e=i!==null;break;case Number:e=i===null?null:Number(i);break;case Object:case Array:try{e=JSON.parse(i)}catch{e=null}}return e}},_t=(i,t)=>!Ot(i,t),gt={attribute:!0,type:String,converter:tt,reflect:!1,useDefault:!1,hasChanged:_t};Symbol.metadata??=Symbol("metadata"),q.litPropertyMetadata??=new WeakMap;var b=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=gt){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){let s=Symbol(),n=this.getPropertyDescriptor(t,s,e);n!==void 0&&Nt(this.prototype,t,n)}}static getPropertyDescriptor(t,e,s){let{get:n,set:o}=zt(this.prototype,t)??{get(){return this[e]},set(r){this[e]=r}};return{get:n,set(r){let c=n?.call(this);o?.call(this,r),this.requestUpdate(t,c,s)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??gt}static _$Ei(){if(this.hasOwnProperty(T("elementProperties")))return;let t=It(this);t.finalize(),t.l!==void 0&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(T("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(T("properties"))){let e=this.properties,s=[...Dt(e),...Ft(e)];for(let n of s)this.createProperty(n,e[n])}let t=this[Symbol.metadata];if(t!==null){let e=litPropertyMetadata.get(t);if(e!==void 0)for(let[s,n]of e)this.elementProperties.set(s,n)}this._$Eh=new Map;for(let[e,s]of this.elementProperties){let n=this._$Eu(e,s);n!==void 0&&this._$Eh.set(n,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){let e=[];if(Array.isArray(t)){let s=new Set(t.flat(1/0).reverse());for(let n of s)e.unshift(Q(n))}else t!==void 0&&e.push(Q(t));return e}static _$Eu(t,e){let s=e.attribute;return s===!1?void 0:typeof s=="string"?s:typeof t=="string"?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),this.renderRoot!==void 0&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){let t=new Map,e=this.constructor.elementProperties;for(let s of e.keys())this.hasOwnProperty(s)&&(t.set(s,this[s]),delete this[s]);t.size>0&&(this._$Ep=t)}createRenderRoot(){let t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return mt(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,s){this._$AK(t,s)}_$ET(t,e){let s=this.constructor.elementProperties.get(t),n=this.constructor._$Eu(t,s);if(n!==void 0&&s.reflect===!0){let o=(s.converter?.toAttribute!==void 0?s.converter:tt).toAttribute(e,s.type);this._$Em=t,o==null?this.removeAttribute(n):this.setAttribute(n,o),this._$Em=null}}_$AK(t,e){let s=this.constructor,n=s._$Eh.get(t);if(n!==void 0&&this._$Em!==n){let o=s.getPropertyOptions(n),r=typeof o.converter=="function"?{fromAttribute:o.converter}:o.converter?.fromAttribute!==void 0?o.converter:tt;this._$Em=n;let c=r.fromAttribute(e,o.type);this[n]=c??this._$Ej?.get(n)??c,this._$Em=null}}requestUpdate(t,e,s,n=!1,o){if(t!==void 0){let r=this.constructor;if(n===!1&&(o=this[t]),s??=r.getPropertyOptions(t),!((s.hasChanged??_t)(o,e)||s.useDefault&&s.reflect&&o===this._$Ej?.get(t)&&!this.hasAttribute(r._$Eu(t,s))))return;this.C(t,e,s)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(t,e,{useDefault:s,reflect:n,wrapped:o},r){s&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,r??e??this[t]),o!==!0||r!==void 0)||(this._$AL.has(t)||(this.hasUpdated||s||(e=void 0),this._$AL.set(t,e)),n===!0&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let t=this.scheduleUpdate();return t!=null&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[n,o]of this._$Ep)this[n]=o;this._$Ep=void 0}let s=this.constructor.elementProperties;if(s.size>0)for(let[n,o]of s){let{wrapped:r}=o,c=this[n];r!==!0||this._$AL.has(n)||c===void 0||this.C(n,void 0,o,c)}}let t=!1,e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(s=>s.hostUpdate?.()),this.update(e)):this._$EM()}catch(s){throw t=!1,this._$EM(),s}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(t){}firstUpdated(t){}};b.elementStyles=[],b.shadowRootOptions={mode:"open"},b[T("elementProperties")]=new Map,b[T("finalized")]=new Map,Bt?.({ReactiveElement:b}),(q.reactiveElementVersions??=[]).push("2.1.2");var at=globalThis,vt=i=>i,G=at.trustedTypes,yt=G?G.createPolicy("lit-html",{createHTML:i=>i}):void 0,St="$lit$",w=`lit$${Math.random().toFixed(9).slice(2)}$`,Et="?"+w,Vt=`<${Et}>`,E=document,O=()=>E.createComment(""),N=i=>i===null||typeof i!="object"&&typeof i!="function",ct=Array.isArray,jt=i=>ct(i)||typeof i?.[Symbol.iterator]=="function",et=`[ 	
\f\r]`,R=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,$t=/-->/g,bt=/>/g,A=RegExp(`>|${et}(?:([^\\s"'>=/]+)(${et}*=${et}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),xt=/'/g,wt=/"/g,Ct=/^(?:script|style|textarea|title)$/i,lt=i=>(t,...e)=>({_$litType$:i,strings:t,values:e}),m=lt(1),re=lt(2),ae=lt(3),C=Symbol.for("lit-noChange"),p=Symbol.for("lit-nothing"),At=new WeakMap,S=E.createTreeWalker(E,129);function kt(i,t){if(!ct(i)||!i.hasOwnProperty("raw"))throw Error("invalid template strings array");return yt!==void 0?yt.createHTML(t):t}var Kt=(i,t)=>{let e=i.length-1,s=[],n,o=t===2?"<svg>":t===3?"<math>":"",r=R;for(let c=0;c<e;c++){let a=i[c],l,u,h=-1,_=0;for(;_<a.length&&(r.lastIndex=_,u=r.exec(a),u!==null);)_=r.lastIndex,r===R?u[1]==="!--"?r=$t:u[1]!==void 0?r=bt:u[2]!==void 0?(Ct.test(u[2])&&(n=RegExp("</"+u[2],"g")),r=A):u[3]!==void 0&&(r=A):r===A?u[0]===">"?(r=n??R,h=-1):u[1]===void 0?h=-2:(h=r.lastIndex-u[2].length,l=u[1],r=u[3]===void 0?A:u[3]==='"'?wt:xt):r===wt||r===xt?r=A:r===$t||r===bt?r=R:(r=A,n=void 0);let y=r===A&&i[c+1].startsWith("/>")?" ":"";o+=r===R?a+Vt:h>=0?(s.push(l),a.slice(0,h)+St+a.slice(h)+w+y):a+w+(h===-2?c:y)}return[kt(i,o+(i[e]||"<?>")+(t===2?"</svg>":t===3?"</math>":"")),s]},z=class i{constructor({strings:t,_$litType$:e},s){let n;this.parts=[];let o=0,r=0,c=t.length-1,a=this.parts,[l,u]=Kt(t,e);if(this.el=i.createElement(l,s),S.currentNode=this.el.content,e===2||e===3){let h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;(n=S.nextNode())!==null&&a.length<c;){if(n.nodeType===1){if(n.hasAttributes())for(let h of n.getAttributeNames())if(h.endsWith(St)){let _=u[r++],y=n.getAttribute(h).split(w),$=/([.?@])?(.*)/.exec(_);a.push({type:1,index:o,name:$[2],strings:y,ctor:$[1]==="."?nt:$[1]==="?"?it:$[1]==="@"?ot:M}),n.removeAttribute(h)}else h.startsWith(w)&&(a.push({type:6,index:o}),n.removeAttribute(h));if(Ct.test(n.tagName)){let h=n.textContent.split(w),_=h.length-1;if(_>0){n.textContent=G?G.emptyScript:"";for(let y=0;y<_;y++)n.append(h[y],O()),S.nextNode(),a.push({type:2,index:++o});n.append(h[_],O())}}}else if(n.nodeType===8)if(n.data===Et)a.push({type:2,index:o});else{let h=-1;for(;(h=n.data.indexOf(w,h+1))!==-1;)a.push({type:7,index:o}),h+=w.length-1}o++}}static createElement(t,e){let s=E.createElement("template");return s.innerHTML=t,s}};function P(i,t,e=i,s){if(t===C)return t;let n=s!==void 0?e._$Co?.[s]:e._$Cl,o=N(t)?void 0:t._$litDirective$;return n?.constructor!==o&&(n?._$AO?.(!1),o===void 0?n=void 0:(n=new o(i),n._$AT(i,e,s)),s!==void 0?(e._$Co??=[])[s]=n:e._$Cl=n),n!==void 0&&(t=P(i,n._$AS(i,t.values),n,s)),t}var st=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){let{el:{content:e},parts:s}=this._$AD,n=(t?.creationScope??E).importNode(e,!0);S.currentNode=n;let o=S.nextNode(),r=0,c=0,a=s[0];for(;a!==void 0;){if(r===a.index){let l;a.type===2?l=new D(o,o.nextSibling,this,t):a.type===1?l=new a.ctor(o,a.name,a.strings,this,t):a.type===6&&(l=new rt(o,this,t)),this._$AV.push(l),a=s[++c]}r!==a?.index&&(o=S.nextNode(),r++)}return S.currentNode=E,n}p(t){let e=0;for(let s of this._$AV)s!==void 0&&(s.strings!==void 0?(s._$AI(t,s,e),e+=s.strings.length-2):s._$AI(t[e])),e++}},D=class i{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,s,n){this.type=2,this._$AH=p,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=s,this.options=n,this._$Cv=n?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode,e=this._$AM;return e!==void 0&&t?.nodeType===11&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=P(this,t,e),N(t)?t===p||t==null||t===""?(this._$AH!==p&&this._$AR(),this._$AH=p):t!==this._$AH&&t!==C&&this._(t):t._$litType$!==void 0?this.$(t):t.nodeType!==void 0?this.T(t):jt(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==p&&N(this._$AH)?this._$AA.nextSibling.data=t:this.T(E.createTextNode(t)),this._$AH=t}$(t){let{values:e,_$litType$:s}=t,n=typeof s=="number"?this._$AC(t):(s.el===void 0&&(s.el=z.createElement(kt(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===n)this._$AH.p(e);else{let o=new st(n,this),r=o.u(this.options);o.p(e),this.T(r),this._$AH=o}}_$AC(t){let e=At.get(t.strings);return e===void 0&&At.set(t.strings,e=new z(t)),e}k(t){ct(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,s,n=0;for(let o of t)n===e.length?e.push(s=new i(this.O(O()),this.O(O()),this,this.options)):s=e[n],s._$AI(o),n++;n<e.length&&(this._$AR(s&&s._$AB.nextSibling,n),e.length=n)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){let s=vt(t).nextSibling;vt(t).remove(),t=s}}setConnected(t){this._$AM===void 0&&(this._$Cv=t,this._$AP?.(t))}},M=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,s,n,o){this.type=1,this._$AH=p,this._$AN=void 0,this.element=t,this.name=e,this._$AM=n,this.options=o,s.length>2||s[0]!==""||s[1]!==""?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=p}_$AI(t,e=this,s,n){let o=this.strings,r=!1;if(o===void 0)t=P(this,t,e,0),r=!N(t)||t!==this._$AH&&t!==C,r&&(this._$AH=t);else{let c=t,a,l;for(t=o[0],a=0;a<o.length-1;a++)l=P(this,c[s+a],e,a),l===C&&(l=this._$AH[a]),r||=!N(l)||l!==this._$AH[a],l===p?t=p:t!==p&&(t+=(l??"")+o[a+1]),this._$AH[a]=l}r&&!n&&this.j(t)}j(t){t===p?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}},nt=class extends M{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===p?void 0:t}},it=class extends M{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==p)}},ot=class extends M{constructor(t,e,s,n,o){super(t,e,s,n,o),this.type=5}_$AI(t,e=this){if((t=P(this,t,e,0)??p)===C)return;let s=this._$AH,n=t===p&&s!==p||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,o=t!==p&&(s===p||n);n&&this.element.removeEventListener(this.name,this,s),o&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}},rt=class{constructor(t,e,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=s}get _$AU(){return this._$AM._$AU}_$AI(t){P(this,t)}};var Wt=at.litHtmlPolyfillSupport;Wt?.(z,D),(at.litHtmlVersions??=[]).push("3.3.3");var Pt=(i,t,e)=>{let s=e?.renderBefore??t,n=s._$litPart$;if(n===void 0){let o=e?.renderBefore??null;s._$litPart$=n=new D(t.insertBefore(O(),o),o,void 0,e??{})}return n._$AI(i),n};var ht=globalThis,v=class extends b{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=Pt(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return C}};v._$litElement$=!0,v.finalized=!0,ht.litElementHydrateSupport?.({LitElement:v});var qt=ht.litElementPolyfillSupport;qt?.({LitElement:v});(ht.litElementVersions??=[]).push("4.2.2");function Gt(i,t,e){return Math.min(Math.max(i,t),e)}function X(i,t,e){return e<=t?.5:Gt((i-t)/(e-t),0,1)}function Xt(i,t,e){if(i==null)return"unknown";if(i<t)return"below";if(i>e)return"above";let s=e-t;if(s<=0)return"in_band";let n=(i-t)/s;return n<.25?"cool_edge":n>.75?"warm_edge":"in_band"}function Mt(i){let{operative:t,setpoint:e,low:s,high:n}=i;if(s==null||n==null||n<=s)return null;let o=s-1.5,r=n+1.5;return{low:s,high:n,span:n-s,operative:t,setpoint:e,category:i.category??"",verdict:Xt(t,s,n),axisLow:o,axisHigh:r,lowFrac:X(s,o,r),highFrac:X(n,o,r),operativeFrac:t==null?null:X(t,o,r),setpointFrac:e==null?null:X(e,o,r)}}var Ut={in_band:"In comfort band",cool_edge:"Cool edge of band",warm_edge:"Warm edge of band",below:"Below comfort band",above:"Above comfort band",unknown:"No reading",preheating:"Pre-heating",coasting:"Coasting",window:"Window open",failure:"Heating failure",learning:"Learning",shadow:"Shadow active",setpoint:"Setpoint",no_entity:"Select a Poise thermostat entity.",min_left:"min",no_system:"Select the Poise System sensor.",sys_title:"Poise System",demand_on:"Boiler demand",demand_off:"No demand",frost:"Frost override",zones:"zones",heating_n:"heating",flow:"Flow",shed:"shed",shadow_would:"would"},Jt={in_band:"Im Komfortband",cool_edge:"Untere Bandkante",warm_edge:"Obere Bandkante",below:"Unter dem Komfortband",above:"\xDCber dem Komfortband",unknown:"Kein Messwert",preheating:"Vorheizen",coasting:"Auslaufen",window:"Fenster offen",failure:"Heizausfall",learning:"Lernt",shadow:"Shadow aktiv",setpoint:"Sollwert",no_entity:"Bitte eine Poise-Thermostat-Entit\xE4t w\xE4hlen.",min_left:"Min",no_system:"Bitte den Poise-System-Sensor w\xE4hlen.",sys_title:"Poise System",demand_on:"Kesselbedarf",demand_off:"Kein Bedarf",frost:"Frost-Override",zones:"Zonen",heating_n:"heizen",flow:"Vorlauf",shed:"abgeworfen",shadow_would:"w\xFCrde"};function f(i,t){return((i??"en").toLowerCase().startsWith("de")?Jt:Ut)[t]??Ut[t]??t}var Zt=[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"climate"}}},{name:"show_shadow",selector:{boolean:{}}}],J=class extends v{setConfig(t){this._config=t}shouldUpdate(t){return t.has("hass")||t.has("_config")}_changed(t){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:t.detail.value}}))}render(){return!this.hass||!this._config?m``:m`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${Zt}
      .computeLabel=${t=>t.name}
      @value-changed=${this._changed}
    ></ha-form>`}};J.properties={hass:{},_config:{state:!0}};customElements.get("poise-card-editor")||customElements.define("poise-card-editor",J);function F(i){let t=typeof i=="string"?parseFloat(i):i;return typeof t=="number"&&!Number.isNaN(t)?t:null}var I=class extends v{static getConfigElement(){return document.createElement("poise-system-card-editor")}static getStubConfig(t){return{type:"custom:poise-system-card",entity:Object.keys(t.states).find(s=>s.startsWith("binary_sensor.")&&t.states[s].attributes.zone_count!==void 0)??""}}setConfig(t){if(!t)throw new Error("Invalid configuration");this._config=t}getCardSize(){return 2}shouldUpdate(t){if(t.has("_config"))return!0;let e=t.get("hass");return!e||!this._config?.entity?!0:e.states[this._config.entity]!==this.hass.states[this._config.entity]}_moreInfo(){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}render(){let t=this.hass?.locale?.language,e=this._config?.entity,s=e?this.hass.states[e]:void 0;if(!s)return m`<ha-card
        ><div class="empty">${f(t,"no_system")}</div></ha-card
      >`;let n=s.attributes,o=s.state==="on",r=F(n.flow_target),c=F(n.shed_count)??0,a=n.source_grants??{},l=Object.keys(a);return m`<ha-card .header=${f(t,"sys_title")}>
      <div class="wrap" @click=${this._moreInfo}>
        <div class="state ${o?"on":""}">
          <ha-icon icon=${o?"mdi:fire":"mdi:fire-off"}></ha-icon>
          <span>${o?f(t,"demand_on"):f(t,"demand_off")}</span>
          ${n.frost_override?m`<em class="frost">${f(t,"frost")}</em>`:p}
        </div>
        <div class="stats">
          <div>
            <strong>${F(n.active_zones)??0}</strong
            ><span>${f(t,"heating_n")}</span>
          </div>
          <div>
            <strong
              >${F(n.controlling_zones)??0}/${F(n.zone_count)??0}</strong
            ><span>${f(t,"zones")}</span>
          </div>
          ${r!=null?m`<div>
                <strong>${r.toFixed(0)}°</strong><span>${f(t,"flow")}</span>
              </div>`:p}
          ${c>0?m`<div>
                <strong>${c}</strong><span>${f(t,"shed")}</span>
              </div>`:p}
        </div>
        ${l.length?m`<div class="grants">
              ${l.map(u=>m`<span class="chip">${u}: ${a[u]}</span>`)}
            </div>`:p}
      </div>
    </ha-card>`}};I.properties={hass:{},_config:{state:!0}},I.styles=H`
    .wrap { padding: 8px 16px 16px; cursor: pointer; }
    .state { display: flex; align-items: center; gap: 8px; font-size: 18px; }
    .state ha-icon { --mdc-icon-size: 22px; color: var(--secondary-text-color); }
    .state.on ha-icon { color: var(--error-color, #d33); }
    .frost { font-style: normal; margin-left: auto; padding: 2px 8px; border-radius: 10px;
      font-size: 11px; background: var(--info-color, #2196f3); color: var(--text-primary-color, #fff); }
    .stats { display: flex; gap: 18px; margin-top: 10px; flex-wrap: wrap; }
    .stats strong { font-size: 20px; }
    .stats span { display: block; font-size: 11px; color: var(--secondary-text-color); }
    .grants { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .chip { padding: 3px 8px; border-radius: 12px; font-size: 12px;
      background: var(--secondary-background-color); }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;var Z=class extends v{setConfig(t){this._config=t}shouldUpdate(t){return t.has("hass")||t.has("_config")}_changed(t){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:t.detail.value}}))}render(){return!this.hass||!this._config?m``:m`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"binary_sensor"}}}]}
      .computeLabel=${t=>t.name}
      @value-changed=${this._changed}
    ></ha-form>`}};Z.properties={hass:{},_config:{state:!0}};customElements.get("poise-system-card-editor")||customElements.define("poise-system-card-editor",Z);customElements.get("poise-system-card")||customElements.define("poise-system-card",I);window.customCards=window.customCards||[];window.customCards.push({type:"poise-system-card",name:"Poise System",preview:!0,description:"Multi-zone boiler demand, flow & load shedding for the Poise hub."});function Ht(i,t,e){return Math.min(Math.max(i,t),e)}function Tt(i,t,e,s=300,n=90,o=1){let r=[];for(let g of i)g.op!=null&&r.push(g.op),g.sp!=null&&r.push(g.sp);if(t!=null&&r.push(t),e!=null&&r.push(e),r.length===0||i.length===0)return null;let c=Math.min(...r)-o,a=Math.max(...r)+o,l=i[0].t,h=i[i.length-1].t-l||1,_=a-c||1,y=g=>(g-l)/h*s,$=g=>n-(g-c)/_*n,k=g=>i.filter(j=>g(j)!=null).map(j=>`${y(j.t).toFixed(1)},${$(g(j)).toFixed(1)}`).join(" ");return{width:s,height:n,opPath:k(g=>g.op),spPath:k(g=>g.sp),bandTop:e==null?0:Ht($(e),0,n),bandBottom:t==null?n:Ht($(t),0,n),vMin:c,vMax:a}}var x={min:16,max:28,start:135,sweep:270};function Yt(i,t,e){return Math.min(Math.max(i,t),e)}function B(i,t=x){let e=Yt((i-t.min)/(t.max-t.min),0,1);return t.start+e*t.sweep}function Qt(i,t=x){let e=i;for(;e<t.start;)e+=360;for(;e>=t.start+360;)e-=360;if(e<=t.start+t.sweep)return e;let s=e-(t.start+t.sweep);return t.start+360-e<s?t.start:t.start+t.sweep}function te(i,t=x){let s=(Qt(i,t)-t.start)/t.sweep;return t.min+s*(t.max-t.min)}function L(i,t,e,s){let n=s*Math.PI/180;return{x:i+e*Math.cos(n),y:t+e*Math.sin(n)}}function pt(i,t,e,s,n){if(n<=s)return"";let o=L(i,t,e,s),r=L(i,t,e,n),c=n-s>180?1:0;return`M ${o.x.toFixed(2)} ${o.y.toFixed(2)} A ${e} ${e} 0 ${c} 1 ${r.x.toFixed(2)} ${r.y.toFixed(2)}`}function Rt(i,t,e=x){let s=Math.atan2(t,i)*180/Math.PI;return s<0&&(s+=360),te(s,e)}var ee="0.54.0";function d(i){let t=typeof i=="string"?parseFloat(i):i;return typeof t=="number"&&!Number.isNaN(t)?t:null}var V=class extends v{constructor(){super(...arguments);this._history=[];this._histFor=null;this._dragging=!1;this._pending=null}static getConfigElement(){return document.createElement("poise-card-editor")}static getStubConfig(e){return{type:"custom:poise-card",entity:Object.keys(e.states).find(n=>n.startsWith("climate.")&&e.states[n].attributes.comfort_low!==void 0)??"",show_shadow:!0}}setConfig(e){if(!e)throw new Error("Invalid configuration");if(e.entity&&!e.entity.startsWith("climate."))throw new Error("Poise card: entity must be a climate entity");this._config={show_shadow:!0,...e}}getCardSize(){return 4}shouldUpdate(e){if(this._dragging||e.has("_config"))return!0;let s=e.get("hass");return!s||!this._config?.entity?!0:s.states[this._config.entity]!==this.hass.states[this._config.entity]}_setpoint(e){let s=this._config.entity;if(!s)return;let n=this.hass.states[s],o=d(n.attributes.target_temperature_step)??.5,r=d(n.attributes.heat_sp)??d(n.attributes.temperature)??21;this.hass.callService("climate","set_temperature",{entity_id:s,temperature:Math.round((r+e*o)*10)/10})}updated(){let e=this._config?.entity;e&&this.hass&&this._histFor!==e&&(this._histFor=e,this._loadHistory(e))}async _loadHistory(e){if(!this.hass.connection)return;let s=new Date,n=new Date(s.getTime()-24*3600*1e3);try{let r=(await this.hass.connection.sendMessagePromise({type:"history/history_during_period",start_time:n.toISOString(),end_time:s.toISOString(),entity_ids:[e],minimal_response:!1,no_attributes:!1}))?.[e]??[],c={},a=[];for(let l of r){l.a&&(c={...c,...l.a});let u=(d(l.lu)??d(l.lc)??0)*1e3;a.push({t:u,op:d(c.operative_temperature)??d(c.current_temperature),sp:d(c.heat_sp)??d(c.temperature)})}this._history=a,this.requestUpdate()}catch{}}_moreInfo(){this._config.entity&&this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_chart(e,s){let n=Tt(this._history,e,s,300,80);return n?m`<svg
      class="chart"
      viewBox="0 0 ${n.width} ${n.height}"
      preserveAspectRatio="none"
    >
      <rect
        x="0"
        y=${n.bandTop}
        width=${n.width}
        height=${Math.max(0,n.bandBottom-n.bandTop)}
        class="cband"
      ></rect>
      <polyline points=${n.spPath} class="csp"></polyline>
      <polyline points=${n.opPath} class="cop"></polyline>
    </svg>`:p}render(){let e=this.hass?.locale?.language,s=this._config?.entity,n=s?this.hass.states[s]:void 0;if(!n)return m`<ha-card
        ><div class="empty">${f(e,"no_entity")}</div></ha-card
      >`;let o=n.attributes,r=d(o.operative_temperature)??d(o.current_temperature),c=d(o.heat_sp)??d(o.temperature),a=Mt({operative:r,setpoint:c,low:d(o.comfort_low),high:d(o.comfort_high),category:o.category??null});return m`<ha-card .header=${o.friendly_name??"Poise"}>
      <div class="wrap">
        ${this._dial(o,e)}
        <div class="verdict">
          ${a?f(e,a.verdict):f(e,"unknown")}
          ${a?.category?m`<span class="cat">Kat. ${a.category}</span>`:p}
        </div>
        ${this._control(this._pending??c,e)}
        ${this._chart(d(o.comfort_low),d(o.comfort_high))}
        ${this._chips(o,e)}
        ${this._learn(o,e)}
      </div>
    </ha-card>`}_dial(e,s){let n=d(e.operative_temperature)??d(e.current_temperature),o=d(e.heat_sp)??d(e.temperature),r=this._pending??o??x.min,c=d(e.comfort_low),a=d(e.comfort_high),l=100,u=100,h=80,_=pt(l,u,h,x.start,x.start+x.sweep),y=c!=null&&a!=null?pt(l,u,h,B(Math.min(c,a)),B(Math.max(c,a))):"",$=L(l,u,h,B(r)),k=n!=null?L(l,u,h,B(n)):null;return m`<div class="dialwrap">
      <svg
        class="dial"
        viewBox="0 0 200 200"
        @pointerdown=${this._onDown}
        @pointermove=${this._onMove}
        @pointerup=${this._onUp}
        @pointercancel=${this._onUp}
      >
        <path class="track" d=${_}></path>
        <path class="bandarc" d=${y}></path>
        <circle
          class="opdot"
          cx=${(k?.x??0).toFixed(1)}
          cy=${(k?.y??0).toFixed(1)}
          r=${k?5:0}
        ></circle>
        <circle class="handle" cx=${$.x.toFixed(1)} cy=${$.y.toFixed(1)} r="9"></circle>
      </svg>
      <div class="dialctr">
        <div class="op">${n!=null?n.toFixed(1):"\u2014"}<span>°C</span></div>
        <div class="soll">${f(s,"setpoint")} <b>${r.toFixed(1)}°</b></div>
      </div>
    </div>`}_fromPointer(e,s){let n=s.getBoundingClientRect();if(!n.width||!this._config.entity)return;let o=(e.clientX-n.left)/n.width*200-100,r=(e.clientY-n.top)/n.height*200-100,c=d(this.hass.states[this._config.entity]?.attributes.target_temperature_step)??.5;this._pending=Math.round(Rt(o,r)/c)*c,this.requestUpdate()}_onDown(e){if(!this._config.entity)return;e.preventDefault();let s=e.currentTarget;s.setPointerCapture(e.pointerId),this._dragging=!0,this._fromPointer(e,s)}_onMove(e){this._dragging&&this._fromPointer(e,e.currentTarget)}_onUp(){if(!this._dragging)return;this._dragging=!1;let e=this._pending;this._pending=null,e!=null&&this._config.entity&&this.hass.callService("climate","set_temperature",{entity_id:this._config.entity,temperature:e}),this.requestUpdate()}_control(e,s){return m`<div class="ctl">
      <ha-icon-button @click=${()=>this._setpoint(-1)} label="-">
        <ha-icon icon="mdi:minus"></ha-icon>
      </ha-icon-button>
      <div class="sp">
        <span>${f(s,"setpoint")}</span
        ><strong>${e!=null?e.toFixed(1):"\u2014"}°C</strong>
      </div>
      <ha-icon-button @click=${()=>this._setpoint(1)} label="+">
        <ha-icon icon="mdi:plus"></ha-icon>
      </ha-icon-button>
    </div>`}_chips(e,s){let n=[];e.preheating&&n.push(this._chip("mdi:fire-circle",f(s,"preheating"),e.minutes_to_comfort,s)),e.coasting&&n.push(this._chip("mdi:coffee",f(s,"coasting"),e.minutes_to_setback,s)),e.window_open&&n.push(this._chip("mdi:window-open",f(s,"window"))),e.heating_failure&&n.push(this._chip("mdi:alert",f(s,"failure")));let o=e.binding_lower_cause;return o&&o!=="en16798"&&n.push(this._chip("mdi:shield-alert",String(o))),n.length?m`<div class="chips" @click=${this._moreInfo}>${n}</div>`:p}_chip(e,s,n,o){let r=d(n);return m`<div class="chip">
      <ha-icon icon=${e}></ha-icon><span>${s}</span>
      ${r!=null?m`<em>${Math.round(r)} ${f(o,"min_left")}</em>`:p}
    </div>`}_learn(e,s){let n=d(e.confidence),o=this._config.show_shadow&&(e.mpc_active||e.tpi_active||e.pi_active),r=d(e.pi_setpoint),c=d(e.mpc_setpoint),a=e.tpi_active?`TPI ${Math.round(d(e.tpi_valve_percent)??0)}%`:e.pi_active&&r!=null?`PI ${r.toFixed(1)}\xB0`:e.mpc_active&&c!=null?`MPC ${c.toFixed(1)}\xB0`:"";return m`<div class="learn">
      ${n!=null?m`<div class="bar">
            <i style="width:${(n*100).toFixed(0)}%"></i>
          </div>
          <span>${f(s,"learning")} ${(n*100).toFixed(0)}%</span>`:p}
      ${o?m`<div class="pill">
            ${f(s,"shadow")}${a?m` · ${a}`:p}
          </div>`:p}
    </div>`}};V.properties={hass:{},_config:{state:!0}},V.styles=H`
    .wrap { padding: 8px 16px 16px; }
    .band {
      position: relative; height: 26px; margin: 8px 0 22px;
      border-radius: 13px; background: var(--divider-color, #e0e0e0);
    }
    .fill {
      position: absolute; top: 0; bottom: 0; border-radius: 13px;
      background: color-mix(in srgb, var(--success-color, #4caf50) 35%, transparent);
    }
    .mark { position: absolute; top: -3px; width: 4px; height: 32px; border-radius: 2px; transform: translateX(-2px); }
    .mark.op { background: var(--primary-color, #2196f3); }
    .mark.sp { background: var(--secondary-text-color, #888); }
    .tick { position: absolute; top: 28px; font-size: 11px; color: var(--secondary-text-color); transform: translateX(-50%); }
    .big { font-size: 40px; font-weight: 600; line-height: 1; }
    .big span { font-size: 18px; color: var(--secondary-text-color); }
    .verdict { color: var(--secondary-text-color); margin-bottom: 8px; }
    .cat { margin-left: 8px; opacity: 0.8; }
    .ctl { display: flex; align-items: center; justify-content: center; gap: 18px; margin: 10px 0 4px; }
    .sp { text-align: center; }
    .sp span { display: block; font-size: 12px; color: var(--secondary-text-color); }
    .sp strong { font-size: 20px; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    .chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .chip ha-icon { --mdc-icon-size: 16px; }
    .chip em { font-style: normal; color: var(--secondary-text-color); }
    .learn { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
    .bar { flex: 1; height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
    .bar i { display: block; height: 100%; background: var(--primary-color); }
    .learn span { font-size: 12px; color: var(--secondary-text-color); }
    .pill { padding: 2px 8px; border-radius: 10px; font-size: 11px;
      background: var(--primary-color); color: var(--text-primary-color, #fff); }
    .chart { width: 100%; height: 80px; margin: 10px 0 2px; display: block; }
    .cband { fill: color-mix(in srgb, var(--success-color, #4caf50) 16%, transparent); }
    .cop { fill: none; stroke: var(--primary-color, #2196f3); stroke-width: 2; vector-effect: non-scaling-stroke; }
    .csp { fill: none; stroke: var(--secondary-text-color, #888); stroke-width: 1.5; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
    .chips { cursor: pointer; }
    .dialwrap { position: relative; width: 100%; max-width: 230px; margin: 6px auto 2px; }
    .dial { width: 100%; display: block; touch-action: none; cursor: pointer; }
    .track { fill: none; stroke: var(--divider-color, #444); stroke-width: 10; stroke-linecap: round; }
    .bandarc { fill: none; stroke: color-mix(in srgb, var(--success-color, #4caf50) 55%, transparent); stroke-width: 10; stroke-linecap: round; }
    .opdot { fill: var(--primary-text-color, #fff); }
    .handle { fill: var(--primary-color, #2196f3); stroke: var(--card-background-color, #1c1c1c); stroke-width: 2; }
    .dialctr { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; }
    .dialctr .op { font-size: 38px; font-weight: 600; line-height: 1; }
    .dialctr .op span { font-size: 16px; color: var(--secondary-text-color); }
    .dialctr .soll { font-size: 13px; color: var(--secondary-text-color); margin-top: 4px; }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;window.customCards=window.customCards||[];window.customCards.push({type:"poise-card",name:"Poise Thermostat",preview:!0,description:"EN-16798 comfort band, operative temperature & shadow state for Poise."});customElements.get("poise-card")||customElements.define("poise-card",V);console.info(`%c POISE-CARD ${ee} `,"background:#2196f3;color:#fff");export{V as PoiseCard};
